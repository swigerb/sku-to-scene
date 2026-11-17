"""Derive the web header logos so the light and dark marks paint at the same visible size.

The two supplied horizontal originals (assets/brand/sku-to-scene-logo-horizontal-{light,dark}.png, 2160x720)
place their artwork on different amounts of transparent padding, so scaling both canvases identically made the
light mark paint about 7% wider than the dark one. This script crops each original to its visible artwork
(alpha > 24), scales it so both marks share one painted width, and centres it on the same transparent 840x176
canvas with the same left inset. The originals are only read, never modified. Pillow is needed only here:

    pip install pillow && python scripts/derive_brand_web.py
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BRAND = REPO / "assets" / "brand"
CANVAS = (840, 176)
PAINTED_WIDTH = 800
LEFT_INSET = (CANVAS[0] - PAINTED_WIDTH) // 2
ALPHA_THRESHOLD = 24
EDGE = 8  # keep the anti-aliased fringe just outside the measured artwork


def visible_box(image):
    return image.getchannel("A").point(lambda a: 255 if a > ALPHA_THRESHOLD else 0).getbbox()


def derive(theme: str) -> tuple[int, int, int, int]:
    from PIL import Image

    original = Image.open(BRAND / f"sku-to-scene-logo-horizontal-{theme}.png").convert("RGBA")
    left, top, right, bottom = visible_box(original)
    crop = original.crop((max(left - EDGE, 0), max(top - EDGE, 0),
                          min(right + EDGE, original.width), min(bottom + EDGE, original.height)))
    scale = PAINTED_WIDTH / (right - left)
    resized = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.Resampling.LANCZOS)
    pad_left, pad_top = (left - max(left - EDGE, 0)) * scale, (top - max(top - EDGE, 0)) * scale
    painted_height = (bottom - top) * scale
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    canvas.alpha_composite(resized, (round(LEFT_INSET - pad_left), round((CANVAS[1] - painted_height) / 2 - pad_top)))
    canvas.save(BRAND / "web" / f"logo-horizontal-{theme}.png", optimize=True)
    return visible_box(canvas)


if __name__ == "__main__":
    for theme in ("light", "dark"):
        box = derive(theme)
        print(f"{theme}: painted box {box} -> {box[2] - box[0]}x{box[3] - box[1]}")
