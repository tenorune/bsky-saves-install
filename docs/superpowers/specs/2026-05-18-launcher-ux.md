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

A real brand mark in `.icns` form, used by Finder, Spotlight, Launchpad, the Dock when the app is visible there, and the `.dmg` background. Source: derived from the GUI's existing icon assets (PWA manifest icons / favicon / dock-ready PNGs in `tenorune/bsky-saves-gui`). Visual identity is shared across the trio — the hosted PWA, the bundled GUI, and the installer all render the same mark.

**Vendoring approach:** commit a copy of the GUI's largest-resolution source PNG into `src/bsky_saves_launcher/resources/` in this repo, and a build-time `iconutil` (or equivalent) step that derives the multi-resolution `.icns` from it. Manual bump when the GUI's brand mark changes (rare). Document the upstream source path in a short header comment next to the resource so the chain of custody is traceable.

Alternative considered and rejected: pulling the icon dynamically from a GUI release tarball at Briefcase build time. Adds network fragility + an extra fetch step; brand marks change rarely enough that manual vendoring is right-sized.

### R2. Custom menu-bar icon (template image)

Replace the runtime-drawn circle with a designed glyph loaded from `resources/`. Constraints specific to macOS menu-bar icons:

- 22pt size at 1x, 44px at 2x — ship at 88px source for safety.
- Monochrome / "template image" convention. macOS handles light/dark and highlight states automatically *if* the NSImage's `setTemplate:` flag is set. pystray does not set it by default; we'll need to reach into pystray's macOS backend (`pystray._darwin.Icon`'s `_status_item`) and call `setImage:` with a template-flagged NSImage via PyObjC. Couples us to pystray's internals; document the patch.

**Source:** derived from the same GUI-owned brand mark used for R1, reduced to a single-color silhouette that scales cleanly to 22pt. If the GUI's existing icon is already silhouette-friendly (a single glyph rather than a richly-coloured illustration), use it directly. If it's not, a single-pass simplification in a vector tool reduces it to a template-image version. Vendor the resulting monochrome PNG (or SVG → PNG export) into `src/bsky_saves_launcher/resources/` alongside the `.icns` source.

### R3. State indicator in the menu-bar icon

Icon variant per supervisor state. The plumbing exists in `tray.py::refresh_icon()`; what's missing is (a) the state-change event wired from the supervisor and (b) variant images.

**Resolved: single template-friendly glyph + small red-dot badge overlay when the helper is in any non-OK state.** Two visual states on the menu-bar icon, mapped from the popover's five-state composite:

| Composite state (in the popover) | Menu-bar treatment |
|---|---|
| running | base glyph, no badge |
| starting | base glyph, no badge (transient; not worth a distinct icon) |
| stopped | base glyph + red badge |
| unresponsive | base glyph + red badge |
| port conflict | base glyph + red badge |

The menu-bar icon is a binary "OK / not OK". The popover names the specific failure mode when the user clicks. Idiomatic on macOS (Calendar, Messages, etc. badge state the same way) and template-image-compatible — the base glyph adapts to light/dark/tinted menu bars; the red badge is a small fixed-color overlay added by Pillow at icon-build time (per-state variant) or composited at runtime.

Rejected alternative: single glyph with color-shift (tinted accent vs gray) to indicate state. Conflicts with the template-image convention — template images can't carry color. Picking that direction would mean accepting that the menu-bar icon doesn't auto-adapt to light/dark/tinted modes, which trades real UX hygiene for a one-line implementation saving.

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

Open: do we ever want the regular policy by default? (E.g., on first launch before the user has expressed a preference, do they see the Dock entry?) **Resolved: hidden by default** (`NSApplicationActivationPolicyAccessory`). The app is a menu-bar daemon from the moment it starts. Reasons: daemon launchers belong in the menu bar by genre convention (Bartender, Hammerspoon, AeroSpace, Rectangle, Stats all default this way); the discoverability problem on first launch is better solved by a one-time onboarding hint pointing at the menu-bar icon than by a permanent Dock presence the user has to toggle off. The onboarding hint itself is out of scope for this spec; flag for the public-release-milestone spec.

### R5. Skip the "Add to Dock" step (PWA-install adjacent) — DEFERRED

**Status:** out of scope for the immediate launcher-UX work. Captured here so the full landscape is documented; the eventual implementer (if/when this is prioritized) has the design space mapped.

The bundled GUI at `http://127.0.0.1:47826/` is a PWA. Today, "Open GUI" opens it as a regular browser tab; the user has to discover the browser's PWA-install affordance themselves to get a Dock-pinned standalone window.

We **cannot** programmatically trigger the browser's PWA-install flow from outside the browser — that's a hard security gate the browser enforces. So "skip the Add to Dock step" reduces to "give the user a Dock-app-like experience without going through the browser's install flow."

#### Catalog of options

In increasing scope:

1. **App-mode Chromium window.** Detect a Chromium-based browser (Chrome, Brave, Edge, Vivaldi, Arc) and launch a chrome-less window via `--app=http://127.0.0.1:47826/`. Looks and behaves like a PWA window without going through the install flow. Single-session — closes when dismissed, no Dock entry persists. ~30 lines of Python + a tray menu item. Firefox has no equivalent flag; would degrade to a regular window.

2. **Bundle a webview inside the launcher.** Embed `pywebview` or PyObjC's `WKWebView` in the launcher process, load the local URL in it. The launcher becomes the Dock entry — clicking the Dock icon brings up the GUI window. Architecturally significant: running a long-lived menu-bar process + a webview window from the same launcher has main-runloop coordination challenges on macOS, and dramatically expands what the launcher is responsible for.

3. **Nativefier-style separate `.app`.** Ship a second `.app` alongside the launcher whose only job is to open the local URL as a Chromium app-mode window. The user has a "Bsky Saves" Dock-pinned shortcut that's distinct from the menu-bar launcher. Coordinating their lifecycles (does quitting the launcher also kill the secondary `.app`? what if the user launches one without the other?) is annoying.

4. **Documentation-only.** Tell the user how to invoke their browser's PWA-install flow manually. No code; lowest effort; relies on the user reading docs. The status quo.

5. **Pre-built Automator/Shortcuts shortcut bundled in the `.dmg`.** Drop a small `.app` (Automator-built or Shortcuts-built) into the `.dmg` alongside the launcher that, when double-clicked, runs the Chromium `--app` invocation. User can drag it to the Dock manually. Lower implementation cost than (3); same UX limitation (manual drag-to-Dock).

6. **Custom WKWebView-based companion in a separate `.app`.** Variant of (3) using Apple's WebKit directly via Swift/Obj-C, not Chromium. Tighter macOS integration, smaller binary, but needs native development outside the Python/Briefcase toolchain. Almost certainly not worth the leap for this project.

7. **Browser extension that detects the URL and prompts install.** Adds a deploy surface (extension on a browser store, install instructions) just to surface the existing PWA-install affordance more aggressively. Architecturally clean for the launcher but moves complexity to a third deliverable.

#### Recommendation when prioritized

Start with (1) — minimal scope, real UX win, doesn't constrain later moves. Revisit (3) or (5) only if (1) proves insufficient (e.g., users want a persistent Dock-pinned shortcut that survives launcher restarts).

#### Open questions for the eventual spec

- **Collapse vs coexist.** If we ship (1) as a new tray action, do we keep the existing "Open GUI" (regular tab) item, or replace it with the new app-mode behavior? Coexisting respects user preference at the moment of action; collapsing is more opinionated about UX. Probably "coexist for v1, collapse later if telemetry justifies."
- **Browser detection order.** Which Chromium variant does the launcher prefer if multiple are installed? User's default browser (if Chromium-based)? Hard-coded preference list? Tray submenu letting the user pick?
- **Fallback when no Chromium found.** Pop a notification ("opens as a regular browser tab; no Chromium browser detected") and fall through to `webbrowser.open()`? Silent fallback? Disable the menu item with a tooltip explaining?
- **Coexistence with helper-served GUI vs hosted PWA.** Does the app-mode window point at `http://127.0.0.1:47826/` (local, requires the helper) or `https://saves.lightseed.net` (hosted, doesn't)? Configurable per the popover's Settings? Different menu items for each?
- **What happens if the user closes the app-mode window?** Does the tray menu item know it's closed? Should re-clicking it open a new window, or focus the existing one? (Browsers don't expose window-lifecycle hooks to external invokers; the launcher can't easily know.)
- **Heavier shapes.** If (1) isn't enough, what's the decision criterion for moving to (3)/(5) vs accepting the friction? Concrete user-feedback trigger needed before the heavier paths earn their cost.

## Open questions

- ~~**Brand identity sequencing.**~~ **Resolved: use the GUI's icon assets as the source of truth.** R1 + R2 + R3 all derive from `tenorune/bsky-saves-gui`'s existing brand mark; visual identity is shared across the trio. Vendor a copy into `src/bsky_saves_launcher/resources/` and bump manually when the GUI's mark changes.
- **Onboarding.** First-launch UX — discoverable menu-bar icon, "we're up here" hint, etc. Out of scope here; flag for the public-release-milestone spec.
- **Accessibility.** Menu-bar icons need to work for users with limited color perception. The badge-overlay direction in R3 helps; flat-color states (running=green) hurt. Worth being explicit when the glyph is designed.

## Cross-references

- `docs/v0.1-lessons.md` — broader v0.1 dry-run learnings.
- `docs/superpowers/specs/2026-05-17-status-window-contents.md` — sibling stub for the status window's *contents*.
- `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md` — v0.1 design, especially § 3.3 (tray module) and § 6 (out of scope).
