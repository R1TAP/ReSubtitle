"""端到端自测：播放模型自带 wav -> WASAPI 环回采集 -> 流式 ASR 实时识别。

用法:  .venv\\Scripts\\python.exe scripts\\e2e_test.py [wav路径]

注意：会通过默认输出设备短暂播放一段测试语音（约 3 秒），
请保持系统非静音，采集的是该输出设备的回环信号。
"""
from __future__ import annotations

import pathlib
import sys
import time
import winsound

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from livesub import config as C  # noqa: E402
from livesub.asr import StreamingASR  # noqa: E402
from livesub.audio import _to_mono_1d, pick_loopback_device  # noqa: E402
from livesub.models import ensure_model  # noqa: E402


def main() -> int:
    wav = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else None
    md = ensure_model()
    if wav is None:
        td = md / "test_wavs"
        wav = sorted(td.glob("*.wav"))[0] if td.exists() else next(md.glob("*.wav"))
    print(f"[e2e] 模型: {md.name}")
    print(f"[e2e] 将播放: {wav.name}（约 3 秒）并通过环回采集实时识别")

    asr = StreamingASR(md)
    finals: list[str] = []
    asr.final.connect(lambda t: (finals.append(t), print(f"[final] {t}")))
    asr.partial.connect(lambda t: print(f"[partial] {t}") if t else None)

    mic = pick_loopback_device()
    print(f"[e2e] 采集设备: {mic.name}")

    winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)

    t0 = time.time()
    n_samples = 0
    with mic.recorder(samplerate=C.AudioConfig().sample_rate, channels=1) as rec:
        rec.record(numframes=480)   # 丢弃启动缓冲
        while time.time() - t0 < 8:
            x = _to_mono_1d(rec.record(numframes=1600))   # 100ms 块
            n_samples += x.shape[0]
            asr.feed(x)
    asr.stop()

    dt = time.time() - t0
    secs = n_samples / 16000.0
    print(f"[e2e] 采集音频 {secs:.1f}s，用时 {dt:.1f}s，实时率 {dt / max(secs, 1e-6):.2f}x")
    print(f"[e2e] 共识别 {len(finals)} 句")
    return 0 if finals else 1


if __name__ == "__main__":
    sys.exit(main())
