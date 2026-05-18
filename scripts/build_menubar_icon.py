"""Derive the menu-bar silhouette PNG from the brand-mark SVG.

macOS menu-bar icons are conventionally template images: a single-color
silhouette that macOS tints automatically based on the menu-bar appearance
(light, dark, tinted). This script:

1. Renders src/bsky_saves_launcher/resources/icon-source.svg at 88px
   via cairosvg.
2. Thresholds the rendered RGBA's alpha channel into a 1-bit silhouette
   mask.
3. Composites a solid-black silhouette onto a transparent 88x88 canvas.
4. Writes src/bsky_saves_launcher/resources/menubar.png.

88px = 22pt @ 4x, which covers all current macOS menu-bar scales with
headroom. pystray reads the PNG and scales down as needed.

Run: python scripts/build_menubar_icon.py
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bsky_saves_launcher" / "resources" / "icon-source.svg"
DEST = ROOT / "src" / "bsky_saves_launcher" / "resources" / "menubar.png"

SIZE = 88
ALPHA_THRESHOLD = 128


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found. See plan Task 1.")
        return 1

    png_bytes = cairosvg.svg2png(
        bytestring=SRC.read_bytes(),
        output_width=SIZE,
        output_height=SIZE,
    )
    rendered = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # Build silhouette mask from alpha (anywhere the SVG painted, we draw).
    alpha = rendered.getchannel("A")
    mask = alpha.point(lambda v: 255 if v >= ALPHA_THRESHOLD else 0)

    # Solid black silhouette on transparent canvas. macOS template-image
    # rendering ignores color and uses alpha; black is the convention.
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    silhouette = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    canvas.paste(silhouette, (0, 0), mask)

    DEST.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(DEST, "PNG")
    print(f"Wrote {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
