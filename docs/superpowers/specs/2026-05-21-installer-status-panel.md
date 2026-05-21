# Installer status panel — library status surface

**Status:** spec, ready to plan.

**Parent:** v0.3.0 popover surface (`docs/superpowers/specs/2026-05-17-status-window-contents.md`; shipped in `docs/superpowers/plans/2026-05-18-v0.3.0-popover.md`).

**Cross-repo contract:** [`installer-status-panel.md`](https://github.com/tenorune/bsky-saves-coordination/blob/main/docs/installer-status-panel.md) on the neutral `bsky-saves-coordination` repo. Resolved-questions archive at [`installer-status-panel-resolved.md`](https://github.com/tenorune/bsky-saves-coordination/blob/main/docs/installer-status-panel-resolved.md). The contract is **canonical**; this spec implements the installer's slice.

**Coordinated repos:**

| Repo | Their slice | Their dependency on this work |
|---|---|---|
| `bsky-saves` (helper) | New `POST /status`, `GET /status`, `DELETE /status` endpoints. Coalesced disk-flush. In-memory TTL for session mode. | The installer can't begin user-visible work until `GET /status` is shipped in a tagged helper release. |
| `bsky-saves-gui` | Pushing the §4.4 payload at the trigger set in §4.3. 15s heartbeat in session mode. `priority: "final"` on `beforeunload`. | Helper-side endpoints must exist before the GUI's pushes have a target. |

The release of all three is coordinated: helper version that ships the endpoints, GUI version that ships the push call, installer version that ships the panel — all three pinned together in the installer's bundle (Appendix A of the contract).

## Background

v0.3.0 shipped the popover surface but only renders launcher-internal state today (helper alive/dead, supervisor uptime, helper + GUI version strings from `/ping`). The actual *library* state — handle, save count, hydration progress — lives in the GUI's browser session and isn't visible to the panel.

The phase-1 contract adds a `GET /status` endpoint on the helper that the GUI pushes summaries to and the installer polls. This spec captures how the installer renders that data inside the existing popover.

**Reference for what's on the wire:** see the contract's §4.4 (payload shape) and §4.5 (panel-side surface). The TL;DR:

- Payload includes: `schema_version`, `updated_at`, `current_state ∈ {idle, refreshing, hydrating, error}`, optional `priority`, `library.{handle, did, total_saves, by_status.{synced, lost, unsaved}}`, `hydration.{articles, threads, images}.{completed, total}`, `storage.{mode, session_ttl_seconds, browser_bytes_estimate}`, `last_activity.{kind, started_at, finished_at, added, removed, errors[]}`.
- All fields are optional. The panel renders only what's present.
- Auth: bearer token, same as `/ping`.
- Cadence: one fetch on popover show, every 5s while visible, no polling closed. **Locked by R10**.
- 404 means "no snapshot yet" (no GUI has ever pushed) or "session-mode snapshot TTL'd out."
- Staleness threshold for the "last seen N min ago" indicator: **5 minutes**. Locked by R10.

## Requirements

### R1. Render library status when available

When `GET /status` returns 200, the panel surfaces the library's current state at a glance. The user's mental model: "is my library healthy, and is anything in flight?" — not a debug dump of the payload.

**Renderable elements (priority order):**

1. **Library identity.** The handle (e.g. `alice.bsky.social`) — short, top-line. DID is informational only, never displayed (it's an opaque identifier, not user-facing). Always present once the user is signed in.
2. **Total saves count.** A single integer ("1,247 saves"). Always present once the user has a non-empty library.
3. **Retention breakdown** (from `library.by_status`). Three integers — synced / lost / unsaved — with `lost` and `unsaved` only rendered when non-zero (zero values are the healthy default and don't need eyeball-time). Visual cue: lost and unsaved values colored to draw attention.
4. **Hydration progress.** Each of `articles`, `threads`, `images` rendered as a horizontal bar with the `completed/total` ratio. Bars sit under the counts. Hydration entries the payload omits are not rendered (the bar disappears, not "loading").
5. **Last activity line.** "Fetch · 2 min ago · +3 / −0" — a single-line summary derived from `last_activity`. Renders `last_activity.kind` mapped to a human label, relative time from `finished_at`, and the +/- counts. When `last_activity.errors` is non-empty, render an error count badge that opens a tooltip with the per-error `{kind, message, count}` triples.
6. **Live state indicator.** When `current_state === "refreshing"` or `"hydrating"`, render a small spinner next to the appropriate row (`refreshing` near "Last activity", `hydrating` near the hydration bars). When `current_state === "error"`, the indicator is suppressed but the errors badge in (5) covers the same information.

Implementation note: there's no `current_state === "fetching"` distinct from `refreshing` in the payload — fetch is a kind of refresh — so the spinner mapping is `refreshing` next to last-activity and `hydrating` next to bars.

### R2. Render the "no snapshot" placeholder

When `GET /status` returns 404 (no GUI has ever pushed, *or* the session-mode TTL expired), the panel shows:

- Headline: "No active library status yet."
- Body: "Open the BSky Saves GUI and let it sync once — it'll show up here."
- Action: a single button — "Open BSky Saves GUI". Tapping opens the Local GUI URL (`http://127.0.0.1:47826/`) via `webbrowser.open` — same as the existing Open GUI button on the default popover panel.

Rationale for using the Local GUI specifically (not `saves.lightseed.net`): the panel can only show data from a paired GUI session pushing to the local helper. Sending the user to the hosted PWA wouldn't be paired with this helper; the panel would stay 404. Local GUI is the only path that resolves the 404.

### R3. Staleness indicator

When `updated_at` in the payload is older than **5 minutes** (locked by R10), render a subtle "last seen N min ago" indicator alongside the data. The data itself remains visible — the user can still read the counts; the staleness is a hint, not a hide. Indicator placement: secondary label below the handle, in the small system font + secondary text color.

When `updated_at` is older than 1 hour, switch the indicator to a relative day/hour format ("last seen 3 h ago" / "last seen yesterday").

The panel does **not** poll-with-backoff. The 5s visibility-gated cadence is the only polling behavior. The contract is explicit: for session mode the helper's TTL is the authoritative liveness signal (the panel sees a 404 transition); for persist mode, the snapshot is expected to linger.

### R4. Panel layout — where the library status lives

The popover currently has two panels (Default and More). The library status is a substantial surface — at the upper bound of what the payload can carry, it's 5–6 rows of meaningful content. The choice:

**Resolved: a third panel, reached from a "Library →" link on Default.** Default panel keeps its at-a-glance helper-state-and-open-buttons compactness. The new Library panel takes over the same popover content area when navigated to, mirroring the Default→More navigation pattern already in v0.3.0.

Default panel adds one new control: a "Library →" link in the bottom-left, mirroring the "More →" link in the bottom-right. The position is intentional: the user reads left-to-right; "Library" is the new primary thing; "More" stays the navigation-to-settings affordance.

**Rejected alternatives:**

- **Inline in the default panel.** Considered. Doesn't fit — the default panel is already tight at v0.3.0's 180pt and adding 5 rows of content would either crowd the existing helper-state surface or push the panel height to ~280–300pt, which feels unwieldy hanging from the menu bar.
- **Replace the More panel.** Considered briefly. Settings (start-at-login, pairing-token copy, quit, version footer) are still primary-access controls; demoting them behind another link would be a regression.
- **A separate window.** Considered. Wrong tool — a window is heavyweight, lives in the Dock/window manager, and breaks the popover's transient-dismiss-on-click-outside affordance. The user wants glance + dismiss, not a window to manage.

### R5. Polling lifecycle

Per R10:

- On popover show (`popoverWillShow:` delegate hook), immediately fire one `GET /status`. Store the result on the StatusPopover instance, render whichever sub-panel is visible (Default's library link state hint, Library panel if it's visible).
- While the popover is visible, schedule a 5s repeat `GET /status` on the existing tray health-poll timer (the one that drives the menu-bar state badge). Co-fetch — no second timer.
- On popover close (`popoverWillClose:`), stop the status fetch. The next show fires a fresh immediate fetch.
- The fetch is best-effort: a network error or 5xx is logged once at debug level and the panel's last good snapshot stays rendered. No retry-with-backoff (per R10).

The auth flow reuses the bearer token already held by the launcher from pairing (read via the existing `bsky_saves_launcher.token` module — same path the popover's "Copy pairing token" uses).

### R6. Default panel — minimal change

The Default panel gets exactly one new element: a "Library →" link on the bottom-left, sized and styled to match the existing "More →" link on the bottom-right. The new link is rendered:

- Greyed-out (disabled style) when the last `GET /status` returned 404. The user can still tap — tapping navigates to the Library panel which renders the §R2 placeholder.
- Normal (link style) when the last fetch returned 200.

This is a deliberate decision to keep the at-a-glance state visible from Default without crowding it. The Library link being disabled is a passive signal that "there's nothing there yet."

### R7. Library panel layout

```
┌────────────────────────────────────────┐
│ ← Back                                 │   ← Top-left link, mirrors More panel
│                                        │
│   alice.bsky.social                    │   ← R1.1 handle, primary label
│   last seen 12 min ago                 │   ← R3 staleness (only if >5 min)
│                                        │
│   1,247 saves                          │   ← R1.2 total, large
│   15 lost · 2 unsaved                  │   ← R1.3 retention breakdown (only non-zero)
│                                        │
│   Hydration                            │
│   Articles   ███████░░░  973 / 1247    │   ← R1.4 bars, one per present feature
│   Threads    ████░░░░░░  412 / 1247    │
│   Images     ███████░░░  856 / 1247    │
│                                        │
│   Fetch · 2 min ago · +3 / −0    [!]   │   ← R1.5 last activity (+ R1.6 spinner)
│                                        │   ← [!] tooltip on errors > 0
└────────────────────────────────────────┘
```

Layout details:

- Width: 300pt (matches Default panel post-v0.3.0).
- Height: variable. Bottom of last-rendered row + a 12pt edge inset. The NSPopover resizes on view-controller swap (mechanism already shipped in v0.3.0).
- All rows are left-aligned. The handle is bold; numerals use the regular system font; bars use `NSLevelIndicator` styled as a continuous gauge.
- Section spacing: the "Hydration" header has a 16pt gap above it (separates counts from progress). Last-activity row has a 12pt gap above (separates progress from history).

### R8. Coordinated release

The panel cannot ship until both:

- The helper has tagged a release with the `POST /status` + `GET /status` + `DELETE /status` endpoints.
- The GUI has tagged a release with the push call (otherwise `GET /status` returns 404 for everyone and the panel only ever shows the placeholder).

The installer's release bundles a pinned helper wheel (`bsky-saves==<version>`) and the GUI is bundled in the helper wheel. The three versions are coordinated; the installer's release notes document the three-way pin.

## Resolved (in the contract, repeated here for visibility)

- **Poll cadence:** visibility-gated, 5s. See R10 in the resolved appendix.
- **Staleness threshold:** 5 minutes.
- **Auth:** existing bearer token from pairing.
- **Failure mode (`POST` fails for the GUI):** non-fatal; next push overwrites. Doesn't affect us; we only `GET`.
- **404 vs empty 200:** 404 only. The contract resolves the ambiguity from the earlier read in §4.2: helper returns 404 when nothing exists; we treat 404 as "no snapshot" and render the placeholder.
- **schema_version forward compat:** render what we recognize, ignore unknown fields. No error UI on a higher schema_version.

## Open questions for the plan

These are sequencing / implementation questions whose answers shape the plan doc but don't need cross-repo agreement.

1. **Bar gauge rendering:** `NSLevelIndicator` (native, less control), `NSProgressIndicator` (native, animatable, less style control), or a custom-drawn CALayer (full control, more code). Lean: `NSLevelIndicator` for the static bars (set rangeMaximum + setIntegerValue) since they don't animate per-tick; the spinner for `current_state ∈ {refreshing, hydrating}` is a separate concern and uses `NSProgressIndicator.indeterminate=YES` per the v0.3.0 spinner pattern.

2. **Numeric formatting:** thousands separators ("1,247" vs "1247"). Lean: thousands separators via `NSNumberFormatter` with the user's locale. Reads more naturally; one line of code.

3. **Errors badge UX:** a small bezel with the error count (e.g. "3 errors") to the right of the last-activity line, with a hover-tooltip via `NSToolTip` listing the `{kind, message, count}` triples — vs a click-to-expand inline disclosure. Lean: tooltip first. Errors are infrequent and aggregating them inline pushes the last-activity row to a multi-line affair. If users find tooltip discovery insufficient we promote to an inline disclosure in a later spec.

4. **Test surface:** the popover's existing tests are sparse because most of the v0.3.0 work is AppKit/PyObjC. The new `/status` fetch + parse path is testable in isolation — separate it into a `bsky_saves_launcher.status` module with: `fetch_status(token, base_url) -> StatusSnapshot | None` (None on 404, error, etc.); `StatusSnapshot` as a dataclass of the §4.4 fields; `format_*` helpers (handle, totals, retention, hydration, last-activity, staleness). All testable. The popover's Library panel reads the dataclass directly. Lean: yes, split this out; tests cover at least the 404 path, the malformed-JSON path, the staleness formatting, and the "fields-present-but-empty" cases (no hydration entries, no errors).

5. **Schema-version forward compat: what changes warrant a panel update?** schema_version=1 today. If GUI introduces schema_version=2 with new fields, the panel ignores unknowns (per the contract). The plan should still note: if a field we currently render is *removed* in a future schema, the panel's renderer should detect missing fields gracefully (already implied by R1's "render only what's present"). The dataclass becomes a tolerant deserializer.

6. **Localization scope:** v0.3.0 is English-only. This spec adds new strings ("last seen", "lost", "unsaved", "Hydration", "Articles" / "Threads" / "Images", "Fetch", "Library", "← Back", error labels for `last_activity.errors.kind`). Lean: keep them inline in the code for now (matches v0.3.0); a localization pass is a separate spec touching the whole launcher, not gated on this work.

7. **What does the GUI push for an empty-library / freshly-signed-in state?** Contract says `library` is "Always present once the user is signed in and has a non-empty inventory." So during initial sign-in before the first fetch, the GUI might omit `library` entirely. The panel needs to render "Signed in as @handle, no saves yet" in that case — handle present, total_saves not. Confirm with GUI team that this maps to `library.handle` present + `library.total_saves` either 0 or absent. (This isn't a contract question — it's the implementation needing to handle a payload shape the contract says is legal.)

## Out of scope

- **Phase 2 commands.** Refresh / export / backup-toggle buttons live behind a contract that doesn't exist yet (§5 of the contract is a sketch). When that spec lands, those controls go into the Library panel as a row below the last-activity line.
- **Phase 3 CLI inventories.** Maintainer-flow tier-1 data needs the helper's `--inventory <path>` flag and is out of phase-1 scope. The Library panel today renders only what `GET /status` returns; when phase 3 lands the panel will render two cards (GUI status + on-disk inventory) per the contract's §6.
- **Localization, accessibility audit, dark-mode contrast review.** Each warrants its own spec.
- **Multi-DID rendering.** Single-slot last-write-wins (R3 in the resolved archive). Phase 3 territory.

## Cross-references

- Cross-repo contract: `bsky-saves-coordination:docs/installer-status-panel.md`.
- Cross-repo resolved archive: `bsky-saves-coordination:docs/installer-status-panel-resolved.md`.
- v0.3.0 popover spec: `docs/superpowers/specs/2026-05-17-status-window-contents.md` (parent).
- v0.3.0 plan: `docs/superpowers/plans/2026-05-18-v0.3.0-popover.md` (mechanics for popover construction, NSPopoverDelegate hooks, NSEvent local monitor, view-controller swapping, animated resize).
- Health model: `src/bsky_saves_launcher/health.py` (existing 5-state composite — the menu-bar badge and status dot consume this; the library panel does *not*, since the panel's data comes from `GET /status`, not from internal supervisor state).
- Token read: `src/bsky_saves_launcher/token.py` (bearer-token loader; reused for the new fetch).
