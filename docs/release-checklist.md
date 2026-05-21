# Pre-release smoke test

Before tagging a `v*.*.*` release, run through this checklist on your Mac. Catches the classes of issue that have surprised us in past releases: stub-binary fork bombs, Gatekeeper bypass needs, missing icons, helper auth failures, AWS WAF blocks, cert-verify failures, asset filename mismatches, icon-cache staleness, etc. CI catches **none** of these — it builds the artifact but does not install it as a real user would.

The whole loop is ~10 minutes once your machine is set up.

> **Naming note.** As of v0.2.1, the app is **`BSky Saves`** (capital S in "BSky"). Pre-v0.2.1 builds were named `Bsky Saves` (lowercase s). When in doubt, use case-insensitive matchers (`pgrep -if`, `pkill -if`) so both spellings hit.

## 0 — One-time setup

You only do this once per machine.

### Outbound firewall apps

If you run Little Snitch, LuLu, or any other outbound-connection firewall: **allow all outbound HTTPS for Python, `briefcase`, and `curl` before starting**. Their default "ask on every new connection" mode silently drops packets to PyPI / GitHub raw / `briefcase-support.s3.amazonaws.com`, which surfaces as `httpx.ConnectError: [Errno 9] Bad file descriptor` — a misleading kernel-level error message with nothing to do with the actual cause. Both `fetch_wheel.py` and `briefcase create`'s support-package download fail identically.

If the smoke run dies with `Bad file descriptor`: this is the first thing to check.

### Python and venv

```sh
# Project requires Python 3.11+. 3.12 or 3.13 are fine.
which python3.12 python3.13 2>/dev/null
# If neither exists:
brew install python@3.13  # or visit https://www.python.org/downloads/macos/

cd /path/to/bsky-saves-install
python3.13 -m venv .venv         # adjust binary as available
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev]"
.venv/bin/briefcase --version    # confirm Briefcase installs
```

### Apple Developer enrollment

Out of scope until the public-release milestone. v0.x.y releases are unsigned; Gatekeeper bypass is the install ritual.

---

## 1 — Sync to the commit you intend to release

The release workflow builds at the tag's commit, not at `main`'s HEAD. They should be the same when you tag, but verify:

```sh
git fetch origin
git checkout main
git pull origin main
git log -1 --oneline   # this is what gets built when you tag
```

If you're testing an unmerged PR's contents instead, check out that branch.

---

## 2 — Reset to a fresh-Mac-like state

Past releases broke in ways that "works on my machine" hid because stale state masked them. Reset before each smoke run:

```sh
# Kill any helper or launcher still alive from a previous test (both
# naming conventions, since pre-v0.2.1 and post-v0.2.1 differ)
pkill -9 -if "Bsky Saves" 2>/dev/null
pkill -9 -if "bsky-saves serve" 2>/dev/null
lsof -nP -iTCP:47826 -sTCP:LISTEN   # should print nothing

# Remove BOTH possible installed .app names
sudo rm -rf "/Applications/Bsky Saves.app" "/Applications/BSky Saves.app"

# Bust macOS icon caches. Multiple caches exist (Finder/LaunchServices,
# Dock, Icon Services); they can keep showing the old icon (or
# Briefcase's bee placeholder) even after the .app is replaced — keyed
# on bundle id, which is stable across our renames. This is the
# #1 confusing symptom of a successful rebuild looking broken.
sudo find /private/var/folders/ \( -name com.apple.dock.iconcache -or -name com.apple.iconservices \) -exec rm -rf {} + 2>/dev/null
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister \
    -kill -r -domain local -domain system -domain user
killall Dock 2>/dev/null
killall Finder 2>/dev/null

# Optional but recommended for a true "fresh user" simulation —
# remove the helper's saved state so we exercise first-run paths
# (token generation, OAuth from scratch, etc.). SKIP this if you
# want to keep your bookmark inventory.
#
# rm -rf ~/Library/Application\ Support/bsky-saves/

# Clear Briefcase caches if you've been iterating builds — forces
# a clean support-package pull and bundling pass:
rm -rf build dist ~/Library/Caches/org.beeware.briefcase/support
```

---

## 3 — Build

```sh
.venv/bin/python scripts/fetch_wheel.py
PIP_FIND_LINKS="$PWD/wheelhouse" .venv/bin/briefcase create macOS
.venv/bin/briefcase build macOS
.venv/bin/briefcase package macOS --adhoc-sign
```

**Note on icon artifacts.** Two committed binaries feed the build: `src/bsky_saves_launcher/resources/icon.icns` (consumed by Briefcase for the app icon, app-switcher, Dock) and `src/bsky_saves_launcher/resources/menubar.png` (consumed by pystray at runtime for the menu-bar icon). Both are regenerated only when the source SVGs change:

```sh
# Regenerate (only when source SVGs change, e.g., brand mark update)
.venv/bin/python scripts/build_iconset.py     # SVG → icon.iconset/ PNGs
.venv/bin/python scripts/build_icns.py        # iconset → icon.icns
.venv/bin/python scripts/build_menubar_icon.py  # menu-bar SVG → menubar.png
```

A normal release build does **not** need these scripts to be re-run — the outputs are committed. If you see Briefcase ship the bee placeholder, check that `src/bsky_saves_launcher/resources/icon.icns` exists (not just `icon.iconset/` — Briefcase wants `.icns` specifically, and v0.2.0's release missed this).

Sanity-check the artifact name:

```sh
ls -la dist/
# Expect: BSky.Saves-X.Y.Z.dmg (or Bsky.Saves-X.Y.Z.dmg for pre-v0.2.1)
# where X.Y.Z matches both `[tool.briefcase] version` in pyproject.toml
# AND the tag you're about to push. If the .dmg name has a stale
# version (e.g. 0.1.0 when you expected 0.2.0), the Briefcase version
# was not bumped — fix and rebuild before continuing.
```

---

## 4 — Install as a user would

```sh
# Find the built .app
APP="$(ls -d build/*/macos/app/*.app | head -n1)"
echo "Built APP: $APP"

# Drag-install into /Applications. Using sudo cp instead of Finder so
# the steps are scriptable; the result is the same.
sudo cp -R "$APP" /Applications/
APP_NAME="$(basename "$APP")"
ls -la "/Applications/$APP_NAME"
```

First launch needs Gatekeeper bypass (unsigned build):

```sh
# Right-click → Open is the documented bypass.
# Scripted equivalent: clear the quarantine attribute:
sudo xattr -dr com.apple.quarantine "/Applications/$APP_NAME"
open "/Applications/$APP_NAME"
```

(For a *real* fresh-Mac test of the install ritual itself, skip the `xattr` line and go through Finder's right-click → Open dialog. Catches Gatekeeper-related regressions.)

---

## 5 — Smoke checklist

Go through these in order. **Stop and investigate at the first failure.** Past releases shipped because the implementer (me) declared "looks good" without running all of these.

### 5.1 Process and port

```sh
pgrep -ifa "Bsky Saves"
# Expect: one line, the .app's stub binary running.

lsof -nP -iTCP:47826 -sTCP:LISTEN
# Expect: one Python process listening on 127.0.0.1:47826.
# If empty: the helper thread didn't start. Check the Console log.
# If multiple: something else is on the port (commonly a pipx-installed
# bsky-saves in another shell); pkill it before continuing.
```

### 5.2 Helper /ping

```sh
curl -s http://127.0.0.1:47826/ping | .venv/bin/python -m json.tool
# Expect: { "name": "bsky-saves", "version": "<expected>", "protocol": "...",
#           "gui_bundled": "<version>", "features": [...] }
# Key checks:
#   - "version" matches wheel-version.txt and pyproject.toml's bsky-saves pin.
#   - "gui_bundled" is a non-empty version string (NOT false, NOT missing).
#     If "gui_bundled" is missing or falsy, --gui was probably dropped from
#     HELPER_ARGV. Past regression (v0.1.x).
```

### 5.3 Menu-bar icon

Visually:
- The icon is a recognizable glyph silhouette (a filled bookmark), **not a generic Briefcase placeholder bee, not a solid square, not a colored circle**.
- **Size**: the icon visually matches the size of neighboring system icons (Wi-Fi, battery, Control Center). If our icon looks noticeably larger than its neighbors, the NSImage logical size isn't being set to 22pt — past regression (v0.2.0/v0.2.1 polish iteration).
- **Alignment**: the icon is vertically centered in its menu-bar slot, not top- or bottom-aligned. If skewed, the source PNG's glyph bbox is off-center within the canvas.
- **Light/dark adaptation**: toggle macOS Appearance between Light and Dark (System Settings → Appearance). The icon should remain readable on both. If it stays solid-black in dark mode (invisible against dark menu bar) or solid-white in light mode, the `setTemplate_` flag didn't stick — past regression (the flag has to be set from inside pystray's `setup=` callback, not directly after Icon construction).
- A menu opens with these items in this order (v0.2.1+):
  - **Show status…**
  - **Open GUI**
  - **Quit**

For pre-v0.2.1 builds, the menu also has **Copy pairing token** between Open GUI and Quit. That item was removed in v0.2.1 because the osascript-driven notification it produced has a "Show" button that opens Script Editor — the action belongs in the future popover button instead.

If the menu is missing items or the order is wrong, `tray.py::run()`'s `pystray.Menu(...)` is out of sync.

### 5.4 Finder, Dock, App Switcher, Spotlight icon

Visually verify the brand icon is **not** the generic Briefcase placeholder (a bee):

- In Finder: navigate to `/Applications/<app>.app`. Icon matches the GUI's brand mark.
- In Spotlight (`Cmd-Space`, type the app name): the search result's icon matches.
- In the App Switcher (`Cmd-Tab`): the icon for the running app matches.
- If the app is currently visible in the Dock (it's hidden by default per a future spec): the Dock icon matches.

If **only Finder shows the new icon** but Dock / App Switcher / Spotlight still show the bee, the macOS icon cache is stale — the bee was cached against the bundle id `net.lightseed.bsky-saves-launcher` and that cache key is stable across renames. Re-run the cache-bust commands in §2 and log out + back in if needed.

If **everything shows the bee**, `icon.icns` is missing from `src/bsky_saves_launcher/resources/` or `pyproject.toml`'s `icon = ...` line is wrong. Briefcase wants `.icns` specifically; `icon.iconset/` (a directory of sized PNGs) is **not** accepted on its own. Run `python scripts/build_icns.py` to generate, commit the result, rebuild.

### 5.5 Open GUI

Click the menu-bar icon → "Open GUI". A browser tab opens to `http://127.0.0.1:47826/`.

Visually verify in the browser:
- The bundled GUI loads (no error page, no 404, no "authentication required" JSON).
- The GUI's chrome (header, navigation) appears.

If you see `{"error": "authentication required"}` JSON: `--gui` is missing from `HELPER_ARGV`. Past regression (v0.1.x).

### 5.6 Sign in and refresh bookmarks (end-to-end)

This is the **load-bearing smoke** — the most common regression site. The AWS WAF, cert-verify, and TLS-fingerprint issues we've hit all only surface here.

In the GUI tab:
- Sign in with your Bluesky handle + app password.
- Trigger a bookmark refresh.
- Verify bookmarks load — not an error message.

If you see an error like:
- **"Couldn't refresh — no working bookmark endpoint: ... :403"** — WAF rejecting the helper's TLS handshake. Check that the launcher-side TLS workaround is enabled (`BSKY_SAVES_TLS_DISABLE` is *unset*).
- **"Couldn't refresh — ... :ConnectError"** — `bsky_ssl_context()` in the bundled helper is failing cert verify. Past regression (bsky-saves 0.6.5; fixed in 0.6.6). Confirm `cat wheel-version.txt` matches a known-good version (≥ 0.6.6).
- **"Couldn't refresh — ... :401"** — credentials issue, not an installer issue. Mint a fresh app password.

### 5.7 Show status (placeholder)

Click the menu-bar icon → "Show status…".
- A dialog or popover should appear. In v0.2.x it's an `osascript display dialog` placeholder; in the Tier-2 release it'll be a real NSPopover.
- Click OK / Close to dismiss.
- The app does not freeze or refuse to dismiss.

### 5.8 Quit

Click the menu-bar icon → "Quit".
- The menu-bar icon disappears within a second.
- `pgrep -ifa "Bsky Saves"` returns nothing.
- `lsof -nP -iTCP:47826 -sTCP:LISTEN` returns nothing.

If a stray helper process survives Quit, the in-thread supervisor isn't being torn down — known limitation but worth catching variance.

### 5.9 Library panel (v0.4.0+)

Requires: helper version that ships `GET /status` + a GUI version that ships the push call. If either is older, the panel will show the placeholder forever — verify your `bsky-saves` and `bsky-saves-gui` pins in `pyproject.toml` cover the contract before running this section.

**5.9.1 Fresh-install, no GUI ever opened**

- Open the popover → click "Library →" link (bottom-left of Default panel).
- Expect: placeholder ("No active library status yet" + body text). "Open BSky Saves GUI" button works and opens `http://127.0.0.1:47826/` in your default browser.
- Expect: Default panel's "Library →" link is rendered greyed-out (disabled control text color).

**5.9.2 GUI signed in, fetch complete**

- Open the local GUI in a browser, sign in to Bluesky, run a fetch.
- Open the popover → click "Library →".
- Expect: handle (bold) shown at top; "1,247 saves" (with thousands separator) below; hydration bars per feature (Articles / Threads / Images) with completion ratios on the right; "Last activity: Fetch · just now · +N / −0".
- Expect: Default panel's "Library →" link is rendered with normal link color (not greyed).

**5.9.3 Hydration in progress**

- Trigger a hydrate cycle in the GUI (e.g. clear hydration cache, run again).
- Open the popover → click "Library →".
- Expect: a small spinner next to the last-activity line while `current_state` is `"refreshing"` or `"hydrating"`. Spinner disappears when state returns to `"idle"`.

**5.9.4 Errors present**

- Trigger an error condition in the GUI (e.g. one save's thread fetch fails).
- Open the popover → click "Library →".
- Expect: a small rounded-bezel "N errors" / "1 error" button next to the last-activity line. Hover the button → tooltip shows `kind: message (×count)` per error.

**5.9.5 Staleness (persist mode)**

- Sign in via the GUI in persist mode, run a fetch.
- Close the GUI tab. Wait at least 5 minutes (the locked staleness threshold).
- Open the popover → click "Library →".
- Expect: data still rendered; a subtle "last seen N min ago" indicator appears below the handle, in the small system font.

**5.9.6 Session-mode TTL expiry → 404 transition**

- Sign in via the GUI in session mode, run a fetch.
- Close the GUI tab. Wait at least 60 seconds (the locked session TTL).
- Open the popover → click "Library →".
- Expect: panel shows the placeholder (the session-mode snapshot TTL'd out on the helper side, helper now returns 404).
- Expect: Default panel's "Library →" link returns to greyed-out within ≤5 seconds of opening the popover (the tray's co-fetch tick refreshes the cache).

**5.9.7 Polling lifecycle**

- With the popover closed: confirm no `/status` requests fire. Easiest signal: `log show --predicate 'process == "BSky Saves"' --last 30s` shouldn't show `_kick_status_fetch` or `_maybe_cofetch_status` activity, and `lsof -nP -iTCP -p $(pgrep -if "BSky Saves") 2>/dev/null` shouldn't show a transient connection to port 47826 every 5s for the status endpoint (the `/ping` tick still fires — that's the menu-bar badge driver).
- Open the popover: an immediate `/status` fetch should fire (visible in helper-side logs if the helper logs requests; otherwise observable as a one-time response in the panel within ~100ms).
- While the popover is visible: `/status` fetches every 5s, co-fetched on the existing health-poll tick — should observe one outbound HTTP request to `127.0.0.1:47826/status` every 5s, no separate timer.
- Close the popover: `/status` polling stops within 5s (the next tick observes the popover is no longer visible).

### 5.10 Logs (debug only, optional)

If anything in 5.x failed and you need to see what the helper wrote:

```sh
# Use case-insensitive match so both old and new app names hit
log show --predicate 'process CONTAINS[c] "Sky Saves"' --last 5m --style compact \
  | tee /tmp/bsky-saves-smoke.log \
  | grep -iE "error|fail|warn|exception|traceback|400|401|403|500"
```

`<private>` redactions may hide useful messages — that's a macOS privacy default. To unredact for debugging (requires admin and is a privacy compromise): install Apple's "Logging" Configuration Profile, or run `sudo log config --mode "private_data:on"`. Revert with `sudo log config --mode "private_data:off"` when done.

---

## 6 — Asset name and integrity check

```sh
DMG="dist/$(ls dist/ | grep '\.dmg$' | head -n1)"
echo "DMG: $DMG"
file "$DMG"
shasum -a 256 "$DMG"

# Confirm filename contains the expected version
EXPECTED_VERSION=$(grep -E '^version = ' pyproject.toml | head -n1 | sed -E 's/.*"([^"]+)".*/\1/')
echo "$DMG" | grep -q "$EXPECTED_VERSION" \
  && echo "✓ filename matches version $EXPECTED_VERSION" \
  || echo "✗ MISMATCH: dmg filename does not contain $EXPECTED_VERSION"
```

If the filename doesn't contain the expected version, `[tool.briefcase] version` is out of sync with what you're about to tag. Don't tag — fix first.

---

## 7 — Verdict

If every check from §5 passed and §6 confirms the right asset name:

- Open the PR (if you haven't), get CI green, merge.
- Create the GitHub release with tag `vX.Y.Z`. CI publishes `<app>-X.Y.Z.dmg` + `SHA256SUMS` automatically.
- Optional: also verify the published `.dmg` from the GitHub release using `shasum -a 256 -c SHA256SUMS` after `curl -O` of both files.

If anything failed:

- Don't tag. File an issue or update the in-progress branch with the fix and re-smoke.
- Add a row to the table below for any new failure mode this run surfaced.

---

## Regressions this catches that CI doesn't

| Issue | When it surfaced | What in this checklist catches it |
|---|---|---|
| `.app` stub binary fork bomb when launcher spawned `sys.executable` | v0.1.x dry-run | §5.1 (process count balloons) |
| Helper `serve` without `--gui` returns `{"error": "authentication required"}` | v0.1.x | §5.5 |
| Tk + pystray runloop conflict — status window never displayed | v0.1.x | §5.7 |
| Briefcase version `0.1.0` while git tag `0.1.1`, `.dmg` filename mismatch | v0.1.0–0.1.2 | §6 |
| `SHA256SUMS` referencing space-named filename that GitHub renames in URL | v0.1.0 | §6 (with post-publish curl + shasum -c check) |
| AWS WAF blocking OpenSSL 3.0.x default cipher list TLS handshake | v0.1.0–0.1.2 era | §5.6 |
| `bsky_saves._net.bsky_ssl_context()` returning a context with no CA bundle → cert verify failures in the Briefcase bundle | bsky-saves v0.6.5 + installer v0.1.3 | §5.6 (with "ConnectError" vs "403" diagnosis) |
| Menu-bar icon being a solid 96.8%-opaque square instead of a glyph silhouette | v0.2.0 plan dry-run | §5.3 (template-image / light-mode visibility) |
| Smoke assertion `gui_bundled is True` could never pass (it's a version string) | v0.1.0 release.yml | §5.2 (manual /ping inspection) |
| `httpx.ConnectError: [Errno 9] Bad file descriptor` on every TCP connect — actually outbound firewall (Little Snitch / LuLu) silently dropping packets | v0.2.0 local dry-run | §0 (allow Python/briefcase/curl in outbound firewall before starting) |
| Briefcase shipping its default bee placeholder for the app icon — `.iconset/` was committed but no `.icns`. Briefcase wants `.icns` specifically and doesn't auto-convert in recent versions. | v0.2.0 release | §5.4 (Finder/Dock/Spotlight/App-Switcher icon check) + §3 note on icon artifacts |
| App icon updated, Finder shows it correctly, but Dock + App Switcher keep showing the bee. macOS icon cache keyed on bundle id, persists across `.app` rebuilds and renames. | v0.2.1 local install | §2 (icon-cache bust + Dock/Finder restart) + §5.4 (cross-surface icon verification) |
| Menu-bar icon noticeably larger than neighboring system icons. pystray passes the PNG to NSImage without `setSize_`; NSImage defaults to the PNG's pixel size (88pt for our 88x88 PNG), 4× the menu-bar's 22pt slot. | v0.2.1 local install | §5.3 (visual size comparison against neighbors) |
| Menu-bar icon stayed black in dark mode (no template adaptation). `setTemplate_(True)` was called immediately after `pystray.Icon(...)` construction, but pystray's `_status_item` isn't created until `Icon.run()` starts — patch silently no-op'd. Fix: call from inside `Icon.run(setup=...)` callback. | v0.2.0/v0.2.1 iteration | §5.3 (Appearance toggle Light/Dark) |
| Copy-pairing-token notification's "Show" button opens Script Editor.app — `osascript display notification` always offers a Show action that opens the script's owner, which the OS thinks is Script Editor. No way to suppress without rewriting the notification path entirely (UserNotifications + PyObjC). | v0.2.0 local install | §5.3 (interact with each menu item, observe surface) — fix in v0.2.1 was to remove the tray item; popover button will land instead |
| `briefcase create` failed at support-package download but `build` + `package` ran anyway because a prior successful `create` had cached the support package on disk — produced a `.app` that looked fine but with stale code. | v0.2.x dry-run | §3 (check each Briefcase command's exit code; don't chain blindly) |

The list grows. Append rows here as new failure modes appear in the wild.
