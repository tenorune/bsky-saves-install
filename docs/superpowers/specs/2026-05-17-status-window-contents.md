# Status-window contents — follow-up spec (stub)

**Status:** stub, not started. Captures requirements as they accrue; expand to a full spec when the work is scheduled.

**Parent:** v0.1 design spec at `docs/superpowers/specs/2026-05-16-bsky-saves-install-v0.1-design.md` § 3.4 (status window surface exists, contents deferred).

## Background

v0.1 ships an `osascript display dialog` placeholder as the status surface (see `docs/v0.1-lessons.md` § 2). The follow-up implementation should be a real in-process popover using PyObjC's `NSPopover` (pystray already pulls `pyobjc` on macOS). Tkinter is **not** an option — Tk and pystray cannot share macOS's main runloop.

State in the system lives in three places:

```
   ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
   │   Launcher   │         │    Helper    │         │     GUI      │
   │  (the .app)  │◄─pings──┤ (bsky-saves  │◄─HTTPS──┤  (browser)   │
   │              │         │   serve)     │         │              │
   └──────────────┘         └──────────────┘         └──────────────┘
```

The popover is part of the launcher process, so:

- **Launcher-internal facts** (version, supervisor state, env vars, locally-persisted prefs) are read directly. No new channel.
- **Helper facts** are read via the helper's HTTP API on `127.0.0.1:47826`. We can only read what the helper exposes; surfacing new helper-side facts means asking the CLI team to grow new endpoints.
- **GUI-only facts** (browser-side state, Pyodide-fallback work the helper isn't aware of) have *no channel today*. Surfacing them requires a relay endpoint on the helper that the GUI POSTs to and the launcher subscribes from. Decided: when this becomes a priority, design it as **GUI → helper → launcher relay**, never GUI → launcher directly. Tracked as a future follow-up spec.

The bigger priorities for this spec are the launcher-internal column and a small set of new helper surfaces. The GUI-relay row is deferred.

## Requirements captured to date

The popover has two views, navigable via a gear/ellipsis icon in the default view's corner (stacked-nav style: tap → swap to the secondary view; back chevron → return).

### Default view

The "is it working / get the token" surface, optimized for glance.

**D1. Composite helper status.** A single status line combining the launcher's internal Supervisor signal (is the helper thread/process alive?) with the helper's own `/ping` response. Possible states with intended wording:

- "running" — supervisor alive AND `/ping` recently 200; show uptime ("running 47 min") and last-seen timestamp.
- "starting" — supervisor alive AND `/ping` not yet 200 (typically a 1–2 s window after launch).
- "stopped" — supervisor dead (helper thread/process exited).
- "unresponsive" — supervisor alive but `/ping` is timing out or erroring; helper is wedged.
- "port conflict" — supervisor dead but something else on `127.0.0.1:47826` is answering `/ping` (commonly a parallel `pipx install bsky-saves`).

The user sees the composite, not the two underlying signals. The discrimination matters only because the failure-mode wording differs per case (e.g. "port conflict" suggests a different remedy than "unresponsive").

**D2. Pairing token, copy-only.** Show a labeled "Copy token" button. The token itself is never displayed in the UI — no truncation, no reveal, no asterisk-mask. The clipboard is the only surface the token's value touches. Behind the button: read the token from `~/Library/Application Support/bsky-saves/token` and write it to the system clipboard. Show a brief "Copied" confirmation (e.g. button label flips to "Copied ✓" for ~1.5 s, then reverts) so the user knows the action took.

**Why D2 matters:** discovered during the v0.1.0 smoke when a user pairing to `saves.lightseed.net` had to navigate `~/Library/Application Support/bsky-saves/` in Finder to find the token file. That's friction we can erase cheaply, and we can do it without ever rendering the token visually.

### Secondary "More" panel

Opened from the default view's gear/ellipsis icon. Settings above; versions as an About footer.

**M1. Show in Dock** — toggle macOS activation policy (Accessory / Regular). Persisted to `~/Library/Application Support/bsky-saves-launcher/preferences.json` (or the project's chosen config path). See sibling spec `2026-05-18-launcher-ux.md` § R4 for the underlying mechanics.

**M2. Start at login** — toggle a LaunchAgent plist at `~/Library/LaunchAgents/net.lightseed.bsky-saves-launcher.plist`. Off by default.

**M3. Quit** — terminates the launcher process (and its supervised helper thread). Same effect as the tray "Quit" item; included here so the popover is a complete control surface when focused.

**M4. About / version footer** — three short lines, small text at the bottom of the panel:
- Launcher version (e.g. "Bsky Saves 0.1.3").
- Bundled helper version (e.g. "bsky-saves 0.6.6") — read from `/ping`.
- Bundled GUI version (e.g. "GUI 0.6.3") — read from `/ping`'s `gui_bundled` field.

### Explicitly out of scope

- **TLS workaround status / env-var overrides.** Power-user debug surface; not user-facing. Available via the env vars themselves + `log show --predicate 'process == "Bsky Saves"'`.
- **Recent log tail / stdout-capture restoration.** Useful for debugging but adds substantial scope (stdout/stderr proxy that doesn't pollute launcher-side output). Defer to a later spec if needed; until then, `log show` covers the debugging use case for anyone who needs it.

### Where each value comes from

| Element | Source | Cost |
|---|---|---|
| D1 status (alive / dead) | Launcher's `Supervisor.is_alive()` | Free |
| D1 status (responsive / wedged / port-conflict) | Helper `/ping` round-trip + comparison with supervisor | Free (calls existing endpoint) |
| D1 uptime, last-seen-OK | Launcher-internal timestamps | Free |
| D2 pairing token | Read `~/Library/Application Support/bsky-saves/token` | Free |
| M1 Show in Dock toggle | `NSApp.setActivationPolicy_()` + local pref file | Free |
| M2 Start at login | Write `~/Library/LaunchAgents/*.plist` | Free |
| M3 Quit | `os._exit(0)` | Free |
| M4 launcher version | `bsky_saves_launcher.__version__` | Free |
| M4 helper version + GUI version | `/ping` payload (cached) | Free |

No new helper endpoints required for this v1.

## Open questions for the full spec

- ~~**Window vs panel?**~~ **Resolved: popover anchored to the tray icon (NSPopover + NSStatusItem button as anchor).** Native, discoverable, dismisses cleanly on click-outside when the user moves on. Live updates work in any container — popover doesn't preclude them; the widget state lives in the model layer regardless of view visibility.
- ~~**Auto-refresh cadence?**~~ **Resolved: event-driven for launcher-internal facts; short-poll fallback for helper facts.** Launcher-internal state changes (supervisor exit, `/ping` becomes-available, log-line arrival, preference toggles) push to subscribed views via callbacks — zero lag, low cost since it's all in-process. Helper-internal facts (anything beyond what's in `/ping` cache) are pulled by short-polling the helper's API while the popover is open, until/unless the helper grows an SSE or WebSocket subscription endpoint we can attach to. The CLI team's `helper-control-endpoints` follow-up is the natural place to spec that subscription channel.
- ~~**Token display privacy.**~~ **Resolved: token is never displayed.** D2 is a copy-only button that puts the token directly on the system clipboard without rendering any characters in the UI. Sidesteps the truncation-vs-mask design space entirely and avoids any need to coordinate threat-model thresholds with the helper team.

## Cross-references

- `docs/v0.1-lessons.md` — broader v0.1 dry-run learnings, several of which inform this spec's framing.
- `tenorune/bsky-saves` `docs/superpowers/specs/2026-05-16-bsky-saves-v0.6.2-session-token.md` — helper-side token model.
