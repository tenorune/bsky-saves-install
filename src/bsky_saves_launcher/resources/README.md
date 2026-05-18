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

The vector source of the GUI's brand mark. Consumed by
`scripts/build_iconset.py` (rendered via cairosvg at each Apple-iconset
size). NOT used for the menu-bar silhouette — that has its own source
in `menubar-source.svg` (see below).

## `menubar-source.svg`

A simpler filled-bookmark glyph used as the source for the menu-bar
silhouette. Distinct from the GUI brand mark so the menu-bar icon
can be a clean single-glyph silhouette without competing detail
(macOS menu-bar template-image rendering benefits from a single
foreground shape — a full-detail brand illustration with backgrounds
and inner negative space renders poorly at 22pt). Consumed by
`scripts/build_menubar_icon.py`.

## `icon.iconset/`

Generated from `icon-source.svg` by `scripts/build_iconset.py` (renders
the SVG at each Apple-iconset size via cairosvg). Committed so
`briefcase build` doesn't require cairosvg on every build machine.
Regenerate after updating `icon-source.svg`.

## `icon.icns`

Apple's single-file icon container, produced from `icon.iconset/` by
`scripts/build_icns.py` (pure-Python via `icnsutil` — no macOS-only
`iconutil` dependency). This is the form Briefcase's macOS support
actually consumes; the `.iconset/` directory alone isn't picked up.
Regenerate after updating the iconset.

## `menubar.png`

Generated from `menubar-source.svg` by `scripts/build_menubar_icon.py`.
Single-color silhouette at 88px (rendered at 256px then cropped to
glyph bbox, recolored to black with anti-aliased alpha, resized into
the 88px canvas centered with safe-area padding). Designed to be
flagged as a macOS template image at runtime via the pystray setup
callback in `src/bsky_saves_launcher/tray.py`. Regenerate after
updating `menubar-source.svg`.
