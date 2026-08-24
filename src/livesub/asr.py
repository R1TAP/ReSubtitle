"""sherpa-onnx 流式识别封装（在线 Zipformer Transducer / Paraformer）。

- 支持两类模型：transducer（encoder/decoder/joiner 三个 onnx）与单文件模型
- modified_beam_search 解码，减少流式重复字
- 应用层能量 VAD：连续静音超过阈值即强制断句提交（环回场景比 sherpa 端点规则更可靠）
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import sherpa_onnx
from PySide6.QtCore import QObject, Signal

from . import config as C


class StreamingASR(QObject):
    """在独立线程中消费音频块，实时产出识别结果。

    partial —— 实时中间结果（边说边出字）
    final   —— 一句话识别完成（静音/端点触发）
    """

    partial = Signal(str)
    final = Signal(str)
    state = Signal(str)
    error = Signal(str)

    def __init__(self, model_dir: str | Path, cfg: C.ASRConfig | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg or C.ASRConfig()
        self.model_dir = Path(model_dir)
        self._lock = threading.Lock()
        self._recognizer = None
        self._stream = None
        self._silence_ms = 0.0          # VAD：连续静音时长
        self._utt_ms = 0.0              # 当前句子累计音频时长（用于最长句长强制 reset）
        self._loop_running = False      # run_loop 标志
        self.final_callbacks: list = []  # final 句子的同步回调（ASR 线程直接调用，用于录制，不受主线程阻塞影响）
        self._last_partial_ts = 0.0     # partial 降频时间戳（ASR 线程侧限流）
        self._partial_acked = True      # 背压：主线程是否已处理完上一个 partial
        self._deferred_partial = None   # 背压：主线程忙时保留的最新文本
        self._last_ack_ts = 0.0         # 背压：最近一次 ack 时间（超时强制恢复用）
        self._build()

    # ------------------------------------------------------------------
    def _build(self):
        md = self.model_dir
        tokens = md / "tokens.txt"

        # 1) transducer：encoder / decoder / joiner
        enc = next(md.glob("encoder*.onnx"), None)
        dec = next(md.glob("decoder*.onnx"), None)
        joiner = next(md.glob("joiner*.onnx"), None)
        if enc and dec and joiner and tokens.exists():
            self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
                tokens=str(tokens),
                encoder=str(enc),
                decoder=str(dec),
                joiner=str(joiner),
                num_threads=self.cfg.num_threads,
                sample_rate=self.cfg.sample_rate,
                feature_dim=80,
                decoding_method=self.cfg.decoding_method,
                max_active_paths=self.cfg.max_active_paths,
                enable_endpoint_detection=self.cfg.enable_endpoint_detection,
                rule1_min_trailing_silence=self.cfg.rule1_min_trailing_silence,
                rule2_min_trailing_silence=self.cfg.rule2_min_trailing_silence,
                rule3_min_utterance_length=self.cfg.rule3_min_utterance_length,
            )
            print(f"[asr] 模型加载完成 (transducer): {md.name}")
        else:
            # 2) 单文件模型（如 Paraformer）
            pf = next(md.glob("paraformer*.onnx"), None) or next(md.glob("model*.onnx"), None)
            if pf is None or not tokens.exists():
                raise FileNotFoundError(
                    f"模型文件不完整: {md}（需要 encoder/decoder/joiner 或单文件模型 + tokens.txt）")
            self._recognizer = sherpa_onnx.OnlineRecognizer.from_paraformer(
                tokens=str(tokens),
                paraformer=str(pf),
                num_threads=self.cfg.num_threads,
                sample_rate=self.cfg.sample_rate,
                feature_dim=80,
                decoding_method="greedy_search",
                enable_endpoint_detection=self.cfg.enable_endpoint_detection,
                rule1_min_trailing_silence=self.cfg.rule1_min_trailing_silence,
                rule2_min_trailing_silence=self.cfg.rule2_min_trailing_silence,
                rule3_min_utterance_length=self.cfg.rule3_min_utterance_length,
            )
            print(f"[asr] 模型加载完成 (single-model): {md.name}")
        self._stream = self._recognizer.create_stream()

    # ------------------------------------------------------------------
    def start(self):
        with self._lock:
            if self._stream is None:
                self._stream = self._recognizer.create_stream()
        self.state.emit("running")

    def run_loop(self, q, max_wait: float = 0.25):
        """ASR 线程主循环：从有界队列取音频块喂入（替代 Qt 跨线程信号，防队列积压）。

        q: queue.Queue（由 Pipeline 传入，capture 线程 put）
        """
        import queue as _queue
        self._loop_running = True
        self.state.emit("running")
        while self._loop_running:
            try:
                samples = q.get(timeout=max_wait)
            except _queue.Empty:
                continue
            try:
                self.feed(samples)
            except Exception as e:  # noqa: BLE001
                print(f"[asr] feed 异常: {e}")
        self.state.emit("stopped")

    def partial_ack(self):
        """主线程处理完一个 partial 后调用：恢复背压并补发最新 deferred 文本。"""
        deferred = None
        with self._lock:
            self._partial_acked = True
            self._last_ack_ts = time.monotonic()
            if self._deferred_partial is not None:
                deferred = self._deferred_partial
                self._deferred_partial = None
                self._partial_acked = False
        if deferred is not None:
            self.partial.emit(deferred)

    def stop_loop(self):
        self._loop_running = False

    def feed(self, samples: np.ndarray):
        """喂入一帧 float32 音频（16k 单声道），立即解码并发出结果。"""
        r = self._recognizer
        if r is None:
            return
        with self._lock:
            st = self._stream
            if st is None:
                return
            samples = np.ascontiguousarray(samples, dtype=np.float32)
            block_ms = samples.shape[0] * 1000.0 / self.cfg.sample_rate
            self._utt_ms += block_ms

            # ---- 能量 VAD：统计连续静音时长 ----
            if self.cfg.vad_enabled:
                rms = float(np.sqrt(np.mean(samples * samples))) if samples.size else 0.0
                if rms < self.cfg.vad_silence_rms:
                    self._silence_ms += block_ms
                else:
                    self._silence_ms = 0.0

            st.accept_waveform(self.cfg.sample_rate, samples)
            while r.is_ready(st):
                r.decode_stream(st)
            text = r.get_result(st).strip()

            endpoint = r.is_endpoint(st)
            vad_commit = self.cfg.vad_enabled and self._silence_ms >= self.cfg.vad_commit_ms
            # 最长单句时长：连续语音也强制提交+reset，防止流状态无限增长（CPU 保护）
            too_long = (
                self.cfg.max_utterance_ms > 0
                and self._utt_ms >= self.cfg.max_utterance_ms
            )
            if endpoint or vad_commit or too_long:
                self.partial.emit("")          # 立即清屏（不受降频限制）
                if text:
                    self.final.emit(text)
                    for cb in self.final_callbacks:   # 同步回调（ASR 线程）：录制等
                        try:
                            cb(text)
                        except Exception as e:  # noqa: BLE001
                            print(f"[asr] final 回调异常: {e}")
                r.reset(st)
                self._silence_ms = 0.0
                self._utt_ms = 0.0
            elif text:
                # partial 背压 + 降频（注意：本方法外层已持 self._lock，此处禁止再嵌套加锁）
                #  - 降频：~250ms 一次（ASR 线程侧限流）
                #  - 背压：主线程未处理完上一个 partial 时跳过 emit，只保留最新文本；
                #    事件队列永不积压（最多 1 个 pending），主线程恢复后由 partial_ack 补发最新
                #  - 防御：主线程超过 2s 未 ack（事件丢失等异常）时强制恢复，防止背压状态永久卡死
                now = time.monotonic()
                if now - self._last_partial_ts >= 0.25:
                    self._last_partial_ts = now
                    do_emit = False
                    if self._partial_acked:
                        self._partial_acked = False
                        self._deferred_partial = None
                        do_emit = True
                    else:
                        self._deferred_partial = text
                        if now - self._last_ack_ts > 2.0:
                            self._partial_acked = True
                            self._last_ack_ts = now
                    if do_emit:
                        self.partial.emit(text)

    def stop(self):
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.input_finished()
                    while self._recognizer.is_ready(self._stream):
                        self._recognizer.decode_stream(self._stream)
                    text = self._recognizer.get_result(self._stream).strip()
                    if text:
                        self.final.emit(text)
                finally:
                    self._stream = None
        self.state.emit("stopped")

    # ------------------------------------------------------------------
    def offline_decode(self, wav_path: str | Path) -> str:
        """离线自测：用流式识别器整段解码一个 16-bit PCM wav（自动转 16k 单声道）。"""
        import wave

        wav_path = Path(wav_path)
        with wave.open(str(wav_path), "rb") as w:
            sr = w.getframerate()
            nch = w.getnchannels()
            sw = w.getsampwidth()
            pcm = w.readframes(w.getnframes())
        if sw != 2:
            raise ValueError("仅支持 16-bit PCM wav")
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if nch == 2:
            x = x[0::2]
        if sr != self.cfg.sample_rate:
            t = np.linspace(0.0, x.shape[0], int(x.shape[0] * self.cfg.sample_rate / sr), endpoint=False)
            x = np.interp(t, np.arange(x.shape[0]), x).astype(np.float32)

        st = self._recognizer.create_stream()
        st.accept_waveform(self.cfg.sample_rate, np.ascontiguousarray(x))
        st.input_finished()
        while self._recognizer.is_ready(st):
            self._recognizer.decode_stream(st)
        return self._recognizer.get_result(st).strip()
