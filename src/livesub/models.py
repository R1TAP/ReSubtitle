"""模型下载/解压的兜底逻辑（支持断点续传与自动重试）。"""
from __future__ import annotations

import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Callable

from . import config as C


def download_with_resume(url: str, dest: Path, progress: Callable[[int, int], None] | None = None) -> None:
    """带断点续传与自动重试的下载。progress(have_bytes, total_bytes)。"""
    have = dest.stat().st_size if dest.exists() else 0
    if have > 0:
        print(f"[models] 断点续传: 已有 {have / 1e6:.0f} MB")
    for attempt in range(8):
        try:
            req = urllib.request.Request(
                url, headers={"Range": f"bytes={have}-", "User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status == 200 and have > 0:
                    # 服务器不支持 Range：清空从头下载
                    have = 0
                    dest.write_bytes(b"")
                total = have + int(r.headers.get("Content-Length") or 0)
                with open(dest, "ab") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        if progress:
                            progress(have, total)
            return
        except Exception as e:  # noqa: BLE001
            print(f"[models] 下载中断（{e}），重试 {attempt + 1}/8 ...")
            time.sleep(2)
    raise RuntimeError(f"下载失败: {url}")


def ensure_model() -> Path:
    """确保模型存在，返回模型目录。优先主模型（X-ASR），其次任意已有模型。"""
    # 1) 优先主模型
    d = C.find_model_dir(prefer=C.MODEL_DIR_NAME)
    if d is not None:
        return d
    # 2) 回退：任意已解压模型
    d = C.find_model_dir()
    if d is not None:
        print(f"[models] 使用已有模型: {d.name}（建议运行 scripts/download_model.py 更新主模型）")
        return d
    # 3) 都没有：下载主模型（download_with_resume 自动断点续传，覆盖不完整残留）
    C.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tarball = C.MODELS_DIR / "model.tar.bz2"
    print(f"[models] 开始下载: {C.MODEL_URL}")
    download_with_resume(C.MODEL_URL, tarball,
                         progress=lambda h, t: print(f"\r[models] {h / 1e6:.0f}/{t / 1e6:.0f} MB", end="", flush=True))
    print()

    print("[models] 解压中 ...")
    with tarfile.open(tarball, "r:bz2") as tf:
        tf.extractall(C.MODELS_DIR, filter="data")

    d = C.find_model_dir(prefer=C.MODEL_DIR_NAME) or C.find_model_dir()
    if d is None:
        raise RuntimeError("模型解压后未找到模型目录，请检查下载是否完整")
    print(f"[models] 就绪: {d}")
    return d
