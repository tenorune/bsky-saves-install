# Resources

Binary assets vendored into the launcher.

## `icon-source.png`

Source: `tenorune/bsky-saves-gui:app/public/icons/icon-512.png`. The
GUI's brand mark is the source of truth for the trio (hosted PWA +
bundled GUI + installer). Update path: re-run the `curl` from
`docs/superpowers/plans/2026-05-18-v0.2.0-icons-and-token.md` Task 1
when the GUI's brand mark changes.

Last updated: 2026-05-18
Upstream commit: 430e2183d4382913cf7701409ef6032ffa60288a

## `icon-source.svg`

The vector source of the same brand mark. Consumed by `scripts/build_iconset.py`
and `scripts/build_menubar_icon.py` (rendered via cairosvg at each target size).

## `icon.iconset/`

Generated from `icon-source.svg` by `scripts/build_iconset.py` (renders the
SVG at each Apple-iconset size via cairosvg). Committed so `briefcase build`
doesn't require cairosvg on every build machine. Regenerate after updating
`icon-source.svg`.

## `menubar.png`

Generated from `icon-source.svg` by `scripts/build_menubar_icon.py`.
Single-color silhouette at 88px, designed to be flagged as a macOS
template image at runtime (the launcher does this via PyObjC). Regenerate
after updating `icon-source.svg`.
