"""ReSubtitle 入口。

用法示例：
  python -m resubtitle.main                  # 正常模式：采集系统音频 -> 实时字幕
  python -m resubtitle.main --demo           # 演示模式：不采集音频，模拟字幕
  python -m resubtitle.main --selftest-capture
  python -m resubtitle.main --selftest-asr
  python -m resubtitle.main --device 扬声器 --font-size 36
"""
from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="resubtitle",
        description="ReSubtitle —— 桌面实时音频转字幕（本地 ASR + 透明字幕叠加窗）",
    )
    p.add_argument("--demo", action="store_true", help="演示模式：不采集音频，循环显示示例字幕")
    p.add_argument("--selftest-capture", action="store_true", help="环回采集自测（打印 5 秒电平）")
    p.add_argument("--selftest-asr", action="store_true", help="ASR 自测（离线识别模型自带 wav）")
    p.add_argument("--selftest-gui", action="store_true", help="GUI 自测：构建窗口与右键菜单后退出")
    p.add_argument("--model-dir", default=None, help="指定模型目录（默认自动查找/下载）")
    p.add_argument("--device", default=None, help="指定环回设备名称子串，如 '扬声器'")
    p.add_argument("--font-size", type=int, default=None, help="字幕字号（默认 30）")
    return p.parse_args()


def _ensure_stdio():
    """pythonw / --windowed 打包下 stdout/stderr 为 None，重定向到空设备避免崩溃。"""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")


def _install_excepthook():
    """未捕获异常：写 fatal_error.log 并弹窗提示（无控制台场景下用户仍能看到错误）。"""
    def hook(exc_type, exc_value, exc_tb):
        import traceback
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        try:
            with open("fatal_error.log", "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            pass
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is None:
                QApplication([])
            QMessageBox.critical(None, "ReSubtitle 错误", text)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = hook


def main() -> int:
    _ensure_stdio()
    _install_excepthook()
    args = parse_args()

    from . import config as C

    settings = C.Settings()
    if args.model_dir:
        settings.asr_model_dir = args.model_dir
    if args.device:
        settings.audio.device_substr = args.device
    if args.font_size:
        settings.ui.font_size = args.font_size

    if args.selftest_capture:
        from .selftest import selftest_capture
        return selftest_capture(settings)
    if args.selftest_asr:
        from .selftest import selftest_asr
        return selftest_asr(settings)
    if args.selftest_gui:
        from .app import selftest_gui
        return selftest_gui(settings)

    from .app import run
    return run(settings, demo=args.demo)


if __name__ == "__main__":
    sys.exit(main())
