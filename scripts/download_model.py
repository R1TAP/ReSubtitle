"""手动下载主模型（X-ASR 960ms 流式中英+标点，int8）并解压，带进度与断点续传。

用法:  .venv\\Scripts\\python.exe scripts\\download_model.py
"""
from __future__ import annotations

import pathlib
import sys
import tarfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from livesub import config as C  # noqa: E402
from livesub.models import download_with_resume  # noqa: E402


def main() -> int:
    if C.find_model_dir(prefer=C.MODEL_DIR_NAME) is not None:
        print(f"主模型已存在: {C.MODEL_DIR_NAME}")
        return 0

    C.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tarball = C.MODELS_DIR / "model.tar.bz2"
    print("开始下载主模型（支持断点续传，请耐心等待）:")
    print(C.MODEL_URL)
    download_with_resume(C.MODEL_URL, tarball,
                         progress=lambda h, t: print(f"\r[models] {h / 1e6:.0f}/{t / 1e6:.0f} MB", end="", flush=True))
    print()

    print("解压中 ...")
    with tarfile.open(tarball, "r:bz2") as tf:
        tf.extractall(C.MODELS_DIR, filter="data")

    d = C.find_model_dir(prefer=C.MODEL_DIR_NAME)
    if d is None:
        raise RuntimeError("解压后未找到主模型目录，请检查下载是否完整")
    print(f"模型就绪: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
