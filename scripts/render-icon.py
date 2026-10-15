from pathlib import Path
from io import BytesIO
import cairosvg
from PIL import Image

root = Path(__file__).resolve().parent.parent
raw = cairosvg.svg2png(
    url=str(root / "resources/images/stocks-source.svg"),
    output_width=25,
    output_height=25,
)
im = Image.open(BytesIO(raw)).convert("RGBA")
im.save(root / "resources/images/menu_icon.png")
