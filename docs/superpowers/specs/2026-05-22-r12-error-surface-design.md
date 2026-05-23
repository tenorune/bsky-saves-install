# R12 error surface — design

> **Status:** approved 2026-05-22. Targets `claude/spec-installer-status-panel`.
> **Contract reference:** [R12 — Semantics of `current_state === "error"`](https://github.com/tenorune/bsky-saves-coordination/blob/main/docs/installer-status-panel-resolved.md#r12--semantics-of-current_state--error).

## Goal

Render `snap.current_state == "error"` in the launcher popover with installer-team-owned UX (R12 point 5), honoring the contract's stickiness (point 2) and restart-resurfacing (point 3) requirements.

## Surface

When `snap.current_state == "error"`:

- **Last-activity row** reads `⚠ Refresh failed: <message>` on a single line in red (`NSColor.systemRedColor()`), tail-truncated to the panel's content width. The tooltip carries the full message.
- **Errors badge** is hidden (the inline message already shows the failure — the badge would double up on the same `last_activity.errors[0]` entry).
- **Spinner** is stopped and `setHidden_(True)` (not in-flight).
- **Handle, totals, hydration bars** remain visible — last-known state is still useful context for the user diagnosing the failure.
- **No retry button.** The Local GUI button above already opens the GUI where the user can retry. R12 leaves this panel-side; we keep the read-only-panel model consistent.

When `snap.current_state != "error"`: rendering is unchanged from today. The badge continues to surface per-asset `last_activity.errors[]` entries (R12 point 1's "do NOT promote" path).

### Stickiness and restart behavior

No client-side timeout, no auto-clear logic. The panel just renders whatever `current_state` is in the latest poll response — when the helper persists `"error"` to disk and survives a launcher restart, the panel naturally re-renders the error on next poll. R12 points 2 and 3 are satisfied by construction.

## Implementation

### `_render_library_section` (`popover.py:~1245`)

Add an `error` branch alongside `refreshing` / `hydrating`:

```python
error = snap.current_state == "error"
refreshing = snap.current_state == "refreshing"
hydrating = snap.current_state == "hydrating"

if error:
    msg = (snap.last_activity.errors[0].message
           if snap.last_activity and snap.last_activity.errors
           else "")
    la_str = f"⚠ Refresh failed: {msg}" if msg else "⚠ Refresh failed"
elif refreshing:
    la_str = "Refreshing…"
elif hydrating:
    la_str = "Backing up…"
else:
    la_str = s.format_last_activity(snap)
```

Text color and tooltip:

```python
h["last_activity_label"].setTextColor_(
    NSColor.systemRedColor() if error else NSColor.labelColor()
)
h["last_activity_label"].setToolTip_(msg if error else "")
```

### Badge gating

```python
if errs and not error:
    # existing badge code
else:
    h["errors_badge_button"].setHidden_(True)
```

### Spinner hygiene (la_row centering fix)

Spinner currently uses `setDisplayedWhenStopped_(False)` — this hides it visually but does NOT detach it from NSStackView's arranged-subview layout, which biases the centered la_inner contents off-center when the spinner is stopped. Fix by toggling `isHidden`, which NSStackView does observe:

```python
spinning = refreshing or hydrating
h["spinner"].setHidden_(not spinning)
if spinning:
    h["spinner"].startAnimation_(None)
else:
    h["spinner"].stopAnimation_(None)
```

(The `setDisplayedWhenStopped_(False)` configuration at build-time stays in as a belt-and-suspenders; `setHidden_` is the load-bearing call.)

### Label sizing

The la_inner stack will grow to fit a long error message and clip past the panel edge. Bound the label width so truncation does the right thing:

- `last_activity_label.setLineBreakMode_(NSLineBreakByTruncatingTail)` once at build time.
- `last_activity_label.widthAnchor().constraintLessThanOrEqualToAnchor_(library_content.widthAnchor(), constant: -16).setActive_(True)` once at build time.

## Tests

No new unit tests. The status-layer formatter (`status.py`) doesn't see `current_state == "error"` — the branch lives entirely in the AppKit-coupled `_render_library_section`, which is not unit-tested today (same as the existing `Refreshing…` / `Backing up…` branches). The change is verified by manual popover testing against a helper snapshot with `current_state == "error"`.

## Out of scope

- **GUI tab-reload caveat** (R12 sub-point 4): on browser reload, the GUI's first push overwrites `"error"` with `"idle"`. Documented in R12 as a known GUI-side limitation, not a panel concern.
- **Independent retry telemetry / banner.** R12 point 5 reserves these to the panel team but we're deliberately starting small — visible inline failure plus the existing Local GUI affordance covers the dogfooding need.
