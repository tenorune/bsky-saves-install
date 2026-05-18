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

### R1. Pairing token, copyable

Show the pairing token (currently stored at `~/Library/Application Support/bsky-saves/token`) so the user has an easy way to grab it for hosted-PWA pairing without rummaging in the filesystem. Render as a short identifier (first 8 hex chars or similar — a recognizable prefix, not the whole secret) with a small "copy" icon next to it that copies the **full** token to the clipboard. The truncated display protects against shoulder-surfing in screenshots while keeping the copy affordance.

**Why it matters:** discovered during the v0.1.0 smoke when a user pairing to `saves.lightseed.net` had to navigate `~/Library/Application Support/bsky-saves/` in Finder to find the token file. That's friction we can erase cheaply.

### R2. Helper version + protocol

From the helper's `/ping` response: `version`, `protocol`, `gui_bundled` (the bundled GUI version string — not a boolean; see lessons doc § 7). Useful for "is this the right helper version?" debugging.

### R3. Helper status indicator

"running" / "starting" / "stopped" mirroring the tray-icon state (which today is just a green/gray dot — see icon-design open question below).

### R4. Recent log tail

The supervisor's ring buffer was originally part of the v0.1 design (200 lines from `bsky-saves serve`'s stdout/stderr). When we moved to in-thread execution we lost stdout/stderr capture; the ring is empty in v0.1. Restoring it requires redirecting `sys.stdout` / `sys.stderr` to a write-through proxy while the helper thread runs — doable, but the global-state side effect on the launcher process needs care.

### R5. Quit button

Mirror of the tray "Quit" menu item, useful when the status window is focused and reaching for the menu bar isn't ergonomic.

## Open questions for the full spec

- ~~**Window vs panel?**~~ **Resolved: popover anchored to the tray icon (NSPopover + NSStatusItem button as anchor).** Native, discoverable, dismisses cleanly on click-outside when the user moves on. Live updates work in any container — popover doesn't preclude them; the widget state lives in the model layer regardless of view visibility.
- ~~**Auto-refresh cadence?**~~ **Resolved: event-driven for launcher-internal facts; short-poll fallback for helper facts.** Launcher-internal state changes (supervisor exit, `/ping` becomes-available, log-line arrival, preference toggles) push to subscribed views via callbacks — zero lag, low cost since it's all in-process. Helper-internal facts (anything beyond what's in `/ping` cache) are pulled by short-polling the helper's API while the popover is open, until/unless the helper grows an SSE or WebSocket subscription endpoint we can attach to. The CLI team's `helper-control-endpoints` follow-up is the natural place to spec that subscription channel.
- **Token display privacy.** R1 calls for truncation. Confirm with the helper team that revealing the first N hex chars doesn't materially weaken the token (which is 32 random hex chars per `bsky-saves token`'s implementation — leaking 8 leaves 24 chars / 96 bits of entropy, still safe).

## Cross-references

- `docs/v0.1-lessons.md` — broader v0.1 dry-run learnings, several of which inform this spec's framing.
- `tenorune/bsky-saves` `docs/superpowers/specs/2026-05-16-bsky-saves-v0.6.2-session-token.md` — helper-side token model.
