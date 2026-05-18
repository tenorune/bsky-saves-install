"""Derive the menu-bar silhouette PNG from the menu-bar source SVG.

macOS menu-bar icons are conventionally template images: a single-color
silhouette that macOS tints automatically based on the menu-bar appearance
(light, dark, tinted). This script:

1. Renders src/bsky_saves_launcher/resources/menubar-source.svg at high
   resolution via cairosvg (256px) so subsequent downsampling has plenty
   of detail to work with.
2. Crops to the bounding box of opaque pixels (any padding inside the
   source SVG is removed so the glyph doesn't appear top-aligned in the
   menu bar slot).
3. Recolors the glyph to solid black while preserving the rendered
   alpha channel (anti-aliased edges survive — no 1-bit threshold).
4. Resizes the cropped glyph to fit the final 88x88 canvas with a small
   safe-area margin, centered.
5. Writes src/bsky_saves_launcher/resources/menubar.png.

88px = 22pt @ 4x. pystray hands the PNG to macOS, which downscales it
to the menu-bar's actual size with proper anti-aliasing. The
`setTemplate:` flag is set at runtime via PyObjC in
src/bsky_saves_launcher/tray.py (a pystray setup callback) so macOS
handles light/dark/tinted mode adaptation.

Run: python scripts/build_menubar_icon.py
"""

from __future__ import annotations

import io
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bsky_saves_launcher" / "resources" / "menubar-source.svg"
DEST = ROOT / "src" / "bsky_saves_launcher" / "resources" / "menubar.png"

# Render at higher resolution than the final canvas so the LANCZOS downsample
# has detail to preserve. macOS will downscale further at runtime.
RENDER_SIZE = 256
# Final canvas size. pystray accepts any size; macOS downscales to ~22pt.
CANVAS_SIZE = 88
# Inner margin so the glyph doesn't kiss the menu-bar slot edges.
PADDING_RATIO = 0.05


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found.")
        return 1

    # 1. Render the SVG at high resolution.
    png_bytes = cairosvg.svg2png(
        bytestring=SRC.read_bytes(),
        output_width=RENDER_SIZE,
        output_height=RENDER_SIZE,
    )
    rendered = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

    # 2. Crop to the bounding box of visible pixels — strips any padding the
    # SVG carries and prevents the glyph from being top- or off-aligned when
    # macOS centers the image in the menu-bar slot.
    bbox = rendered.getchannel("A").getbbox()
    if bbox is None:
        print("ERROR: rendered SVG has no visible pixels.")
        return 1
    glyph = rendered.crop(bbox)

    # 3. Recolor to solid black, preserve the rendered alpha (no thresholding —
    # smooth anti-aliased edges survive downsampling).
    alpha = glyph.getchannel("A")
    silhouette = Image.new("RGBA", glyph.size, (0, 0, 0, 0))
    silhouette.paste((0, 0, 0, 255), (0, 0), alpha)

    # 4. Resize the cropped glyph to fit inside CANVAS_SIZE with safe-area
    # padding. Maintain aspect ratio; longest side fills the inner box.
    inner = int(CANVAS_SIZE * (1 - 2 * PADDING_RATIO))
    glyph_w, glyph_h = silhouette.size
    scale = inner / max(glyph_w, glyph_h)
    new_w = max(1, int(round(glyph_w * scale)))
    new_h = max(1, int(round(glyph_h * scale)))
    resized = silhouette.resize((new_w, new_h), Image.LANCZOS)

    # 5. Center on a transparent canvas.
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    x = (CANVAS_SIZE - new_w) // 2
    y = (CANVAS_SIZE - new_h) // 2
    canvas.paste(resized, (x, y), resized)

    DEST.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(DEST, "PNG")
    print(f"Wrote {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
