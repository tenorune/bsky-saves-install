# Launcher UX — follow-up spec (stub)

**Status:** stub, not started. Captures the launcher-presentation UX questions raised after v0.1.3 shipped; expand to a full spec when the work is scheduled.

**Parent:** v0.1 design spec at `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md`. The companion stub spec `2026-05-17-status-window-contents.md` covers the *content* of the status window; this one covers the launcher's *outward* presentation (icons, dock visibility, GUI window framing).

## Background

v0.1.3 ships a working `.app` with:

- A flat green/gray dot drawn at runtime as the menu-bar icon.
- Briefcase's default app icon for the Finder/Dock/Spotlight entry (a generic stencil — fine for dogfood, not for a public release).
- Default macOS app activation policy (the app appears in the Dock and Cmd-Tab while running).
- "Open GUI" opens `http://127.0.0.1:47826/` as a regular browser tab.

For the public-release milestone we want richer, more intentional presentation. This spec gathers the questions.

## Requirements captured to date

### R1. Custom app icon

A real brand mark in `.icns` form, used by Finder, Spotlight, Launchpad, the Dock when the app is visible there, and the `.dmg` background. Source: a single high-resolution PNG; build a multi-resolution `.icns` via `iconutil` or equivalent.

Open: who designs the brand mark? Sketches of two or three directions (e.g., bookmark + cloud, open-book-with-tilde, compass, derived from `bsky-saves-gui`'s favicon) before locking. The icon work is small but a one-way door once it ships.

### R2. Custom menu-bar icon (template image)

Replace the runtime-drawn circle with a designed glyph loaded from `resources/`. Constraints specific to macOS menu-bar icons:

- 22pt size at 1x, 44px at 2x — ship at 88px source for safety.
- Monochrome / "template image" convention. macOS handles light/dark and highlight states automatically *if* the NSImage's `setTemplate:` flag is set. pystray does not set it by default; we'll need to reach into pystray's macOS backend (`pystray._darwin.Icon`'s `_status_item`) and call `setImage:` with a template-flagged NSImage via PyObjC. Couples us to pystray's internals; document the patch.

Open: glyph design (should pair with the brand mark from R1 but be silhouette-friendly).

### R3. State indicator in the menu-bar icon

Icon variant per supervisor state — "running" (helper /ping succeeds), "starting" (subprocess up, /ping not yet 200), "stopped" (subprocess exited). The plumbing exists in `tray.py::refresh_icon()`; what's missing is (a) the state-change event wired from the supervisor and (b) variant images.

Two visual design directions:

- **Single glyph, color-shift state.** Tinted accent color when running, gray when stopped. Conflicts with the template-image convention (template images can't carry color). Choosing this means accepting that the menu bar icon will not auto-adapt to dark mode.
- **Single glyph, badge overlay.** Template-friendly base glyph + small red dot in a corner when the helper is stopped or crashed. Idiomatic on macOS; matches how Calendar, Messages, etc. badge state.

Recommendation: badge overlay. Stay in the template-image lane.

### R4. Hide app from Dock (user preference)

Toggleable "Show in Dock" preference. Default: hidden (menu-bar-only is the right default for a daemon launcher). Persist the user's choice in
`~/Library/Application Support/bsky-saves-launcher/preferences.json` (or wherever fits the project's config convention).

Implementation: PyObjC, `NSApp.setActivationPolicy_(...)`:

- `NSApplicationActivationPolicyAccessory` → no Dock entry, no Cmd-Tab presence, menu-bar only.
- `NSApplicationActivationPolicyRegular` → standard Dock + Cmd-Tab.

Applied on startup based on the persisted preference. Toggle exposed as a tray menu item or status-window checkbox.

Known macOS quirks:
- Switching policies *during* a running session sometimes flashes the Dock icon briefly.
- Rarely, the menu-bar icon disappears momentarily on switch.

Apps shipping this pattern in production: Hammerspoon, Alfred, Bartender. The rough edges are real but minor.

Open: do we ever want the regular policy by default? (E.g., on first launch before the user has expressed a preference, do they see the Dock entry?) The argument for "hidden by default": daemon launchers typically belong in the menu bar. The argument against: a first-launch Dock entry is more discoverable. Probably "hidden by default, but show a one-time onboarding hint pointing at the menu-bar icon on first launch."

### R5. Skip the "Add to Dock" step (PWA-install adjacent)

The bundled GUI at `http://127.0.0.1:47826/` is a PWA. Today, "Open GUI" opens it as a regular browser tab; the user has to discover the browser's PWA-install affordance themselves to get a Dock-pinned standalone window.

We **cannot** programmatically trigger the browser's PWA-install flow from outside the browser — that's a hard security gate the browser enforces.

What we *can* do, in increasing scope:

1. **App-mode Chrome/Chromium window.** Detect a Chromium-based browser (Chrome, Brave, Edge, Vivaldi) and launch a chrome-less window via `--app=http://127.0.0.1:47826/`. Looks and behaves like a PWA window without going through the install flow. Single-session — closes when dismissed. ~30 lines of Python + a tray menu item ("Open as standalone window"). Doesn't persist as a Dock entry.

2. **Bundle a webview.** Embed `pywebview` or PyObjC's WKWebView inside the launcher, load the local URL in it. We become the Dock entry. Real but architecturally significant — running a long-lived menu-bar process + a webview window from the same launcher has main-runloop coordination challenges on macOS, and dramatically expands what the launcher is responsible for.

3. **Nativefier-style separate `.app`.** Ship a second `.app` alongside the launcher whose only job is to open the local URL as a Chrome-app-mode window. Coordinating their lifecycles is annoying but it produces a real "Bsky Saves" Dock-pinned shortcut.

Recommendation: ship **(1)** as a tray menu item in the public-release milestone, and call it explicit-not-implicit. Decide on (2) or (3) separately, possibly never.

## Open questions

- **Brand identity sequencing.** R1 + R2 + R3 (all icon-design) share a source asset. Sketch the brand mark first as a single small decision; don't try to design four things at once.
- **Onboarding.** First-launch UX — discoverable menu-bar icon, "we're up here" hint, etc. Out of scope here; flag for the public-release-milestone spec.
- **Accessibility.** Menu-bar icons need to work for users with limited color perception. The badge-overlay direction in R3 helps; flat-color states (running=green) hurt. Worth being explicit when the glyph is designed.

## Cross-references

- `docs/v0.1-lessons.md` — broader v0.1 dry-run learnings.
- `docs/superpowers/specs/2026-05-17-status-window-contents.md` — sibling stub for the status window's *contents*.
- `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md` — v0.1 design, especially § 3.3 (tray module) and § 6 (out of scope).
