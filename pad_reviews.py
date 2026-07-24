"""One-off utility: letterbox review screenshots from FC/ into FC_slideshow/
so Telegram's slideshow block (which crops photos to fill a portrait frame)
doesn't cut off text. Re-run any time new files are added to FC/.
"""
from pathlib import Path

from PIL import Image

SRC_DIR = Path(__file__).parent / "FC"
DST_DIR = Path(__file__).parent / "FC_slideshow"
CANVAS_SIZE = (1080, 1920)  # 9:16, matches Telegram's slideshow/story frame
BG_COLOR = (10, 10, 16)  # near-black, matches the dark-mode chat screenshots

DST_DIR.mkdir(exist_ok=True)

for src in sorted(SRC_DIR.glob("*.jpg"), key=lambda p: int(p.stem)):
    im = Image.open(src).convert("RGB")
    scale = min(CANVAS_SIZE[0] / im.width, CANVAS_SIZE[1] / im.height)
    new_size = (round(im.width * scale), round(im.height * scale))
    resized = im.resize(new_size, Image.LANCZOS)

    canvas = Image.new("RGB", CANVAS_SIZE, BG_COLOR)
    offset = ((CANVAS_SIZE[0] - new_size[0]) // 2, (CANVAS_SIZE[1] - new_size[1]) // 2)
    canvas.paste(resized, offset)

    canvas.save(DST_DIR / src.name, quality=92)
    print(f"{src.name}: {im.size} -> {new_size} on {CANVAS_SIZE} canvas")

print(f"\nDone. {len(list(DST_DIR.glob('*.jpg')))} files written to {DST_DIR}")
