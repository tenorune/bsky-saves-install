"""Derive the menu-bar silhouette PNG from the menu-bar source SVG.

macOS menu-bar icons are conventionally template images: a single-color
silhouette that macOS tints automatically based on the menu-bar appearance
(light, dark, tinted). This script:

1. Renders the SVG once at a probe size to measure the glyph's bounding
   box (the SVG carries some internal padding).
2. Re-renders at the pixel size that makes the glyph's bbox land exactly
   on INNER_PX — no PIL resize step in the pipeline, so cairosvg's
   vector rasterizer produces the final pixels directly. Eliminates the
   slight edge softness from the previous render-then-LANCZOS chain.
3. Crops to the bbox, recolors to solid black with anti-aliased alpha,
   centers on an 88×88 canvas.

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

# Final canvas pixel size. The launcher additionally sets the NSImage's
# *logical* size to 22pt via PyObjC (see tray.py::_flag_macos_template_image),
# matching Apple's menu-bar template-image convention. 88px = 22pt @ 4x retina.
CANVAS_SIZE = 88
# Glyph fills ~70% of the slot ≈ 15.4pt visible, matching Apple HIG.
PADDING_RATIO = 0.15
INNER_PX = int(round(CANVAS_SIZE * (1 - 2 * PADDING_RATIO)))

# Probe-render size for measuring the SVG's content bbox. Any reasonable
# size works; this just needs to give us the bbox-to-svg ratio.
PROBE_SIZE = 128


def _render_and_bbox(svg_bytes: bytes, size: int):
    png_bytes = cairosvg.svg2png(
        bytestring=svg_bytes,
        output_width=size,
        output_height=size,
    )
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    bbox = img.getchannel("A").getbbox()
    return img, bbox


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found.")
        return 1

    svg_bytes = SRC.read_bytes()

    # 1. Probe-render to find the glyph's bbox at PROBE_SIZE.
    _probe, probe_bbox = _render_and_bbox(svg_bytes, PROBE_SIZE)
    if probe_bbox is None:
        print("ERROR: rendered SVG has no visible pixels.")
        return 1
    probe_w = probe_bbox[2] - probe_bbox[0]
    probe_h = probe_bbox[3] - probe_bbox[1]

    # 2. Compute the cairosvg output size that makes the bbox's longer
    # side equal INNER_PX, then re-render at that resolution. The
    # rasterizer now produces final-resolution pixels directly — no
    # PIL resize needed downstream.
    target_render = int(round(PROBE_SIZE * (INNER_PX / max(probe_w, probe_h))))
    rendered, bbox = _render_and_bbox(svg_bytes, target_render)
    if bbox is None:
        print("ERROR: second-pass render has no visible pixels.")
        return 1
    glyph = rendered.crop(bbox)

    # 3. Recolor to solid black, preserving the anti-aliased alpha so the
    # edges stay smooth at the rasterized pixel size.
    alpha = glyph.getchannel("A")
    silhouette = Image.new("RGBA", glyph.size, (0, 0, 0, 0))
    silhouette.paste((0, 0, 0, 255), (0, 0), alpha)

    # 4. Center on the final transparent canvas. No resize step.
    canvas = Image.new("RGBA", (CANVAS_SIZE, CANVAS_SIZE), (0, 0, 0, 0))
    gx, gy = silhouette.size
    x = (CANVAS_SIZE - gx) // 2
    y = (CANVAS_SIZE - gy) // 2
    canvas.paste(silhouette, (x, y), silhouette)

    DEST.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(DEST, "PNG")
    print(f"Wrote {DEST} (glyph {gx}x{gy} in {CANVAS_SIZE}x{CANVAS_SIZE} canvas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
