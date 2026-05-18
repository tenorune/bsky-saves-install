"""Derive the Apple iconset from icon-source.svg at every required size.

Renders the vector source via cairosvg at each target size — sharper than
upscaling a single raster across all sizes. Output is a directory of
sized PNGs in Apple's iconset naming convention; Briefcase's macOS
support converts that into a .icns at build time.

Apple iconset spec:
  https://developer.apple.com/library/archive/documentation/GraphicsAnimation/Conceptual/HighResolutionOSX/Optimizing/Optimizing.html

Run: python scripts/build_iconset.py
"""

from __future__ import annotations

from pathlib import Path

import cairosvg

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "bsky_saves_launcher" / "resources" / "icon-source.svg"
DEST = ROOT / "src" / "bsky_saves_launcher" / "resources" / "icon.iconset"

# (size_in_px, filename) — Apple's iconset naming convention.
SIZES: list[tuple[int, str]] = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]


def main() -> int:
    if not SRC.exists():
        print(f"ERROR: {SRC} not found. See plan Task 1.")
        return 1

    svg_bytes = SRC.read_bytes()
    if DEST.exists():
        for child in DEST.iterdir():
            child.unlink()
    DEST.mkdir(parents=True, exist_ok=True)

    for size, name in SIZES:
        out = DEST / name
        png_bytes = cairosvg.svg2png(
            bytestring=svg_bytes,
            output_width=size,
            output_height=size,
        )
        out.write_bytes(png_bytes)
        print(f"  wrote {out} ({size}x{size})")

    print(f"Done. iconset at {DEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
