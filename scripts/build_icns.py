"""Build src/.../resources/icon.icns from the iconset directory.

Briefcase's macOS support wants `<icon>.icns` (Apple's single-file
icon container), not `<icon>.iconset/` (the directory of sized PNGs).
On macOS the conventional builder is `iconutil -c icns`, but that's
macOS-only. icnsutil is a pure-Python equivalent that produces a
valid `.icns` from PNG inputs on any platform.

Run: python scripts/build_icns.py
"""

from __future__ import annotations

from pathlib import Path

import icnsutil

ROOT = Path(__file__).resolve().parent.parent
ICONSET = ROOT / "src" / "bsky_saves_launcher" / "resources" / "icon.iconset"
DEST = ROOT / "src" / "bsky_saves_launcher" / "resources" / "icon.icns"


def main() -> int:
    if not ICONSET.is_dir():
        print(f"ERROR: {ICONSET} not found. Run scripts/build_iconset.py first.")
        return 1

    png_files = sorted(ICONSET.glob("icon_*.png"))
    if not png_files:
        print(f"ERROR: no icon_*.png files in {ICONSET}.")
        return 1

    icns = icnsutil.IcnsFile()
    for png in png_files:
        icns.add_media(file=str(png))
        print(f"  added {png.name}")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    icns.write(str(DEST))
    print(f"Wrote {DEST} ({DEST.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
