"""无需 GUI 的自测命令。"""
from __future__ import annotations

import time

import numpy as np

from . import config as C
from .audio import _to_mono_1d, pick_loopback_device


def selftest_capture(settings: C.Settings, seconds: float = 5.0) -> int:
    """环回采集自测：打印 N 秒电平，验证能听到系统正在播放的声音。"""
    try:
        mic = pick_loopback_device(settings.audio)
    except RuntimeError as e:
        print(f"[selftest] {e}")
        return 1

    print(f"[selftest] 采集设备: {mic.name}")
    print(f"[selftest] 接下来 {seconds:.0f} 秒采集环回音频，请播放一段声音观察电平 ...")
    sr = settings.audio.sample_rate
    with mic.recorder(samplerate=sr, channels=1) as rec:
        rec.record(numframes=int(sr * 0.3))   # 丢弃启动缓冲
        t0 = time.time()
        while time.time() - t0 < seconds:
            x = _to_mono_1d(rec.record(numframes=int(sr * 0.1)))
            rms = float(np.sqrt(np.mean(x * x)))
            peak = float(np.abs(x).max())
            bar = "#" * int(min(50, rms * 200))
            print(f"\r[{time.time() - t0:4.1f}s] RMS={rms:.4f} peak={peak:.4f} {bar}", end="", flush=True)
    print("\n[selftest] 完成。若 RMS 随播放声音明显变化，说明环回采集正常。")
    return 0


def selftest_asr(settings: C.Settings) -> int:
    """ASR 自测：用流式识别器离线解码模型自带的 wav，验证模型与封装可用。"""
    from pathlib import Path

    from .asr import StreamingASR
    from .models import ensure_model

    md = Path(settings.asr_model_dir) if settings.asr_model_dir else ensure_model()
    asr = StreamingASR(md, settings.asr)

    test_dir = md / "test_wavs"
    wavs = sorted(test_dir.glob("*.wav")) if test_dir.exists() else sorted(md.glob("*.wav"))
    if not wavs:
        print(f"[selftest] 模型目录 {md} 下未找到测试 wav")
        return 1

    ok = 0
    for w in wavs:
        t0 = time.time()
        text = asr.offline_decode(w)
        dt = time.time() - t0
        print(f"[selftest] {w.name} ({dt:.2f}s) -> {text}")
        if text:
            ok += 1
    print(f"[selftest] 完成：{ok}/{len(wavs)} 条识别出文字")
    return 0 if ok else 1
