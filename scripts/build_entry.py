"""PyInstaller 打包入口（仅打包时使用，不参与运行时）。

一键打包：双击 scripts\\build_exe.bat（或项目根执行该脚本内容）。
"""
from __future__ import annotations

import pathlib
import sys

# 源码运行时把 src 加入路径；PyInstaller 打包后 resubtitle 已收集进包内，此目录不存在则跳过
_src = pathlib.Path(__file__).resolve().parent.parent / "src"
if _src.exists():
    sys.path.insert(0, str(_src))

try:
    from resubtitle.main import main  # noqa: E402
except ModuleNotFoundError as e:  # noqa: F841
    # 打包不完整（如漏了 --paths src）：给出可读提示而非裸 traceback
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        QApplication([])
        QMessageBox.critical(
            None, "ReSubtitle 启动失败",
            "程序模块加载失败（resubtitle 未被打包完整）。\n"
            "请重新运行 scripts\\build_exe.bat 重新打包后再试。\n\n" + str(e))
    except Exception:
        pass
    raise

if __name__ == "__main__":
    sys.exit(main())
