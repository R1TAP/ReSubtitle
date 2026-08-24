"""生成程序图标：logo.svg -> logo.png (256px) + logo.ico（多尺寸）。

用法:  .venv\\Scripts\\python.exe scripts\\make_icon.py [svg路径]
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
svg_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "logo.svg"
if not svg_path.exists():
    sys.exit(f"未找到 {svg_path}")

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
renderer = QSvgRenderer(str(svg_path))
size = 256
img = QImage(size, size, QImage.Format.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
renderer.render(p)
p.end()
png_path = ROOT / "logo.png"
ok = img.save(str(png_path))
if not ok:
    sys.exit("QImage.save 失败（缺少 png 插件？）")
print(f"PNG: {png_path}")

from PIL import Image

img256 = Image.open(str(png_path)).convert("RGBA")
ico_path = ROOT / "logo.ico"
img256.save(str(ico_path), format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print(f"ICO: {ico_path}")
print("ICON_OK")
