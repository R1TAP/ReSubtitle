"""WASAPI 环回采集：捕捉系统正在播放的声音（16kHz 单声道 float32）。

依赖 soundcard（纯 Python + ctypes 封装 WASAPI），无需安装任何驱动。
"""
from __future__ import annotations

import queue
import time

import numpy as np
from PySide6.QtCore import QObject, Signal

try:
    import soundcard as sc
except ImportError:  # pragma: no cover
    sc = None

from . import config as C


def _to_mono_1d(data: np.ndarray) -> np.ndarray:
    """把 soundcard 返回的数据规整为 (N,) float32。"""
    x = np.asarray(data)
    if x.ndim == 2:
        # soundcard 不同版本返回 (channels, frames) 或 (frames, channels)
        if x.shape[0] == 1:
            x = x[0]
        elif x.shape[1] == 1:
            x = x[:, 0]
        else:
            x = x[0]
    return np.ascontiguousarray(x, dtype=np.float32)


def pick_loopback_device(cfg: C.AudioConfig | None = None):
    """选择回环采集设备（供 LoopbackCapture 与自测共用）。

    优先级：显式指定名称子串 > 与默认输出设备同名的回环设备 > 第一个回环设备。
    """
    cfg = cfg or C.AudioConfig()
    if sc is None:
        raise RuntimeError("soundcard 未安装：pip install soundcard")
    mics = sc.all_microphones(include_loopback=True)
    if not mics:
        raise RuntimeError("未找到任何 WASAPI 环回采集设备")
    sub = cfg.device_substr.strip().lower()
    if sub:
        for m in mics:
            if sub in m.name.lower():
                return m
        raise RuntimeError(
            f"未找到名称包含 '{sub}' 的回环设备，可用: " + "; ".join(m.name for m in mics))
    # 优先选择与“默认输出”同名的回环设备
    try:
        default = sc.default_speaker().name
    except Exception:
        default = ""
    for m in mics:
        if default and default.lower() in m.name.lower():
            return m
    return mics[0]


class LoopbackCapture(QObject):
    """在独立线程中循环采集系统回环音频。支持运行中切换设备（热重启采集循环）。

    音频分发：
      - samples_queue 非空：put 到有界队列（满则丢最旧，保证实时性，防 Qt 信号积压）
      - 否则通过 samples 信号发出（默认，兼容旧用法）
    """

    samples = Signal(object)   # np.ndarray float32 (N,)，交给 ASR
    level = Signal(float)      # 0~1 电平指示（调试/显示用）
    state = Signal(str)        # 'running' / 'stopped'
    error = Signal(str)

    def __init__(self, cfg: C.AudioConfig | None = None, samples_queue: queue.Queue | None = None,
                 parent=None):
        super().__init__(parent)
        self.cfg = cfg or C.AudioConfig()
        self._samples_queue = samples_queue
        self.recorder_cb = None          # 录制音频落盘回调（同线程直接调用，零事件开销）
        self._running = False
        self._device_changed = False   # 置位后内层采集循环退出，外层按新设备重启

    # ------------------------------------------------------------------
    def set_device(self, substr: str):
        """切换监听设备（名称子串，空串=自动选择默认输出）。"""
        self.cfg.device_substr = substr
        self._device_changed = True
        print(f"[audio] 设备切换请求: {substr or '自动'}")

    # ------------------------------------------------------------------
    def _queue_put(self, x: np.ndarray):
        """放入有界队列；满则丢弃最旧一帧再放入（保证实时性，防积压）。"""
        q = self._samples_queue
        if q is None:
            return
        try:
            q.put_nowait(x)
        except queue.Full:
            try:
                q.get_nowait()
            except queue.Empty:
                pass
            try:
                q.put_nowait(x)
            except queue.Full:
                pass

    # ------------------------------------------------------------------
    def run(self):
        """采集主循环（应在独立线程中执行）。设备切换或采集退化时自动重启采集循环。"""
        self._running = True
        self.state.emit("running")
        sr = self.cfg.sample_rate
        n = max(1, int(sr * self.cfg.chunk_ms / 1000))
        # WASAPI 环回启动初期（重采样/缓冲就绪）可能出现数据间隙，属正常现象
        if sc is not None:
            import warnings
            warnings.filterwarnings("ignore", category=getattr(sc, "SoundcardRuntimeWarning", Warning))
        last_restart = 0.0
        try:
            while self._running:
                self._device_changed = False
                mic = pick_loopback_device(self.cfg)
                print(f"[audio] 采集设备: {mic.name}")
                with mic.recorder(samplerate=sr, channels=1) as rec:
                    try:
                        rec.record(numframes=int(sr * 0.3))   # 丢弃启动缓冲
                    except Exception:
                        pass
                    silent_since = time.monotonic()
                    while self._running and not self._device_changed:
                        data = rec.record(numframes=n)
                        x = _to_mono_1d(data)
                        rms = float(np.sqrt(np.mean(x * x))) if x.size else 0.0
                        now = time.monotonic()
                        if rms > 0.003:
                            silent_since = now
                        elif now - silent_since > 5.0 and now - last_restart > 15.0:
                            # 采集 watchdog：连续静音 5s 且距上次重启 >15s，
                            # 判定 WASAPI 环回采集退化（蓝牙/虚拟声卡长时间运行常见），
                            # 退出内层循环 -> 外层重新初始化采集以自愈
                            print("[audio] 采集停滞检测，自动重启采集循环")
                            last_restart = now
                            break
                        self.level.emit(min(1.0, rms * self.cfg.level_scale))
                        if self.recorder_cb is not None:
                            try:
                                self.recorder_cb(x)
                            except Exception:  # noqa: BLE001
                                pass
                        if self._samples_queue is not None:
                            self._queue_put(x)
                        else:
                            self.samples.emit(x)
        except Exception as e:  # noqa: BLE001
            if self._running:
                self.error.emit(str(e))
                print(f"[audio] 采集异常: {e}")
        finally:
            self._running = False
            self.state.emit("stopped")

    def stop(self):
        self._running = False
