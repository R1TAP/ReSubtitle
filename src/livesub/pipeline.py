"""把 采集 → ASR → 字幕窗 装配起来的流水线。

线程模型（v3，防积压 + 无 QThread）：
  采集线程（threading.Thread + LoopbackCapture.run）─ put ─▶ 有界队列（maxsize=8，满丢最旧）
                                                              │ get（阻塞，0.25s 超时轮询）
                                                              ▼
   ASR 线程（threading.Thread + StreamingASR.run_loop）─ emit partial/final ─▶ 主线程字幕窗
  录制会话（可选）：采集线程直接回调写音频，final 信号记录时间轴

注意：采集/ASR 线程使用纯 Python threading.Thread 而非 QThread——
实测 PySide6 的 QThread 在跑阻塞循环时会使主线程 Qt 事件循环的定时器/UI 完全饿死
（表现为运行一段时间后程序卡死、停止转录无响应）。
"""
from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject

from . import config as C
from .asr import StreamingASR
from .audio import LoopbackCapture


class Pipeline(QObject):
    def __init__(self, settings: C.Settings, window, session=None, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.window = window
        self.session = session   # 可选：录制会话（RecordingSession）

        self._audio_queue: queue.Queue = queue.Queue(maxsize=8)
        self.capture = LoopbackCapture(settings.audio, samples_queue=self._audio_queue)
        self.asr = StreamingASR(settings.asr_model_dir, settings.asr)

        self._capture_thread = threading.Thread(
            target=self.capture.run, name="livesub-capture", daemon=True)
        self._asr_thread = threading.Thread(
            target=lambda: self.asr.run_loop(self._audio_queue),
            name="livesub-asr", daemon=True)

        # 音频：采集线程 -> 有界队列 -> ASR 线程
        # ASR 结果：partial 经背压后上屏（见 asr.partial_ack），final 直接提交
        self.asr.partial.connect(self._on_partial)
        self.asr.final.connect(self.window.commit)
        self.asr.state.connect(lambda s: print(f"[asr] {s}"))
        self.capture.state.connect(lambda s: print(f"[audio] {s}"))
        self.capture.error.connect(self._on_error)
        self.asr.error.connect(self._on_error)
        # 录制会话：句子时间轴（ASR 线程同步回调，主线程阻塞也不丢句）
        #          + 音频落盘（采集线程直接回调，零事件开销）
        if self.session is not None:
            self.asr.final_callbacks.append(self.session.on_final)
            self.capture.recorder_cb = self.session.feed_audio
        # 右键菜单切换监听设备
        self.window.request_set_device.connect(self.set_device)

    # ---- partial 背压：处理后 ack，ASR 线程据此决定是否继续 emit ----
    def _on_partial(self, text: str):
        try:
            self.window.set_partial(text)
        finally:
            self.asr.partial_ack()

    def _on_error(self, msg: str):
        print(f"[pipeline] 错误: {msg}")
        self.window.commit(f"[采集异常] {msg}")

    def start(self):
        """启动采集与 ASR 线程。支持反复启停（停止后重建线程）。"""
        if not self._capture_thread.is_alive():
            self._capture_thread = threading.Thread(
                target=self.capture.run, name="livesub-capture", daemon=True)
        if not self._asr_thread.is_alive():
            self._asr_thread = threading.Thread(
                target=lambda: self.asr.run_loop(self._audio_queue),
                name="livesub-asr", daemon=True)
        self._capture_thread.start()
        self._asr_thread.start()

    def stop(self):
        """停止采集与 ASR 线程并清理队列。可随后再次 start()。"""
        self.capture.stop()
        self.asr.stop_loop()
        self.asr.stop()
        self._capture_thread.join(timeout=3)
        self._asr_thread.join(timeout=3)
        # 清空残留音频块，避免下次启动处理旧数据
        while True:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

    def set_device(self, substr: str):
        """切换监听设备（名称子串，空串=自动）。采集循环热重启，ASR 保持运行。"""
        self.window.current_device_substr = substr
        print(f"[pipeline] 切换监听设备: {substr or '自动'}")
        self.capture.set_device(substr)

