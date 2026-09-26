from PIL import Image
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
assets_dir = root / "src" / "assets"
src_png = assets_dir / "icon.png"

if not src_png.exists():
    print(f"Error: {src_png} not found")
    exit(1)

img = Image.open(str(src_png)).convert("RGBA")
# Save ICO with multiple sizes
ico_path = assets_dir / "icon.ico"
img.save(str(ico_path), format="ICO",
         sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])

print(f"Updated {ico_path}")
