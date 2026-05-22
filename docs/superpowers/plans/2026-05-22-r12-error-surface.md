# R12 Error Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render `snap.current_state == "error"` inline in the launcher popover's last-activity row, and fix the la_row off-center bias by hiding the stopped spinner from NSStackView's arranged-subview layout.

**Architecture:** Single-file change in `src/bsky_saves_launcher/popover.py`. Build-time changes pin label truncation and width; render-time changes add the `error` branch (red text, message inline, tooltip with full message), gate the existing errors badge on `not error`, and toggle `spinner.setHidden_` so the stopped spinner doesn't reserve layout space.

**Tech Stack:** PyObjC / AppKit (NSTextField, NSProgressIndicator, NSColor, NSLineBreakByTruncatingTail).

**Spec:** `docs/superpowers/specs/2026-05-22-r12-error-surface-design.md`.

---

### Task 1: Build-time label sizing for truncation

**Files:**
- Modify: `src/bsky_saves_launcher/popover.py:269-272` (where `last_activity_label` is constructed in `_build_default_view`).

**Why:** Long error messages would grow la_inner past `library_content`'s width and either clip oddly or break the equal-spacer centering. Constrain the label to ≤ `library_content.width − 16pt` and enable tail truncation up front.

- [ ] **Step 1: Add the AppKit import**

In the `from AppKit import (...)` block inside `_build_default_view` (popover.py:184-204), add `NSLineBreakByTruncatingTail` alphabetically:

```python
    from AppKit import (  # type: ignore[import-not-found]
        NSBezelStyleRounded,
        NSButton,
        NSControlSizeSmall,
        NSFont,
        NSLevelIndicator,
        NSLevelIndicatorStyleContinuousCapacity,
        NSLineBreakByTruncatingTail,
        NSProgressIndicator,
        ...
    )
```

- [ ] **Step 2: Set truncation mode and max-width constraint on `last_activity_label`**

Right after `last_activity_label.setFont_(...)` at popover.py:271, before `la_inner.addArrangedSubview_(last_activity_label)`:

```python
    last_activity_label = NSTextField.labelWithString_("")
    last_activity_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    last_activity_label.setLineBreakMode_(NSLineBreakByTruncatingTail)
    # Bound the label width so a long error message can't expand la_inner
    # past the panel's content width and break the equal-spacer centering.
    try:
        last_activity_label.widthAnchor().constraintLessThanOrEqualToAnchor_constant_(
            library_content.widthAnchor(), -16.0
        ).setActive_(True)
    except Exception:
        pass
    la_inner.addArrangedSubview_(last_activity_label)
```

Note the PyObjC method spelling: `constraintLessThanOrEqualToAnchor_constant_` (with the `_constant_` suffix on the variant that takes a constant offset).

- [ ] **Step 3: Verify lint and tests still pass**

Run: `uv run ruff check src/ tests/ && uv run --extra dev pytest tests/ -q`

Expected: lint clean, all tests pass (no new tests; existing 88 should remain green).

- [ ] **Step 4: Commit**

```bash
git add src/bsky_saves_launcher/popover.py
git commit -m "Bound last_activity_label width for truncation

Sets NSLineBreakByTruncatingTail and constrains the label's width to
library_content - 16pt so long error strings (per R12) can't stretch
la_inner past the panel and break centering."
```

---

### Task 2: Spinner centering fix (toggle setHidden_)

**Files:**
- Modify: `src/bsky_saves_launcher/popover.py:1259-1267` (the spinner start/stop block in `_render_library_section`).

**Why:** `setDisplayedWhenStopped_(False)` hides the spinner visually but does NOT detach it from NSStackView's arranged-subview layout — la_inner keeps reserving the spinner's slot, biasing the label off-center when the spinner is stopped. NSStackView observes `isHidden`, so toggling that is the load-bearing call.

- [ ] **Step 1: Replace the spinner start/stop block**

Replace the existing block at ~popover.py:1259:

```python
        try:
            if refreshing or hydrating:
                h["spinner"].startAnimation_(None)
            else:
                h["spinner"].stopAnimation_(None)
        except Exception:
            pass
```

with:

```python
        spinning = refreshing or hydrating
        try:
            h["spinner"].setHidden_(not spinning)
            if spinning:
                h["spinner"].startAnimation_(None)
            else:
                h["spinner"].stopAnimation_(None)
        except Exception:
            pass
```

- [ ] **Step 2: Verify lint and tests still pass**

Run: `uv run ruff check src/ tests/ && uv run --extra dev pytest tests/ -q`

Expected: lint clean, all tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/bsky_saves_launcher/popover.py
git commit -m "Hide stopped spinner from la_inner layout

setDisplayedWhenStopped_(False) hides the spinner visually but
NSStackView still reserves its arranged-subview slot, which biased
the last-activity label off-center. Toggling setHidden_ — which
NSStackView observes — detaches the stopped spinner from layout so
the label centers cleanly when neither spinner nor badge is shown."
```

---

### Task 3: R12 error render branch

**Files:**
- Modify: `src/bsky_saves_launcher/popover.py:1245-1257` (the in-flight detection + la_str block).
- Modify: `src/bsky_saves_launcher/popover.py:1269-1283` (the errors badge block).

**Why:** Spec section "Surface" and "Implementation hook" — add the fourth branch alongside `refreshing` / `hydrating` / default, paint the label red with a tooltip, and gate the errors badge so it doesn't double-up on the inline message.

- [ ] **Step 1: Add NSColor import for the renderer's helpers**

`NSColor` is already imported inline at popover.py:96 inside `_status_dot_color`, but `_render_library_section` is in a different scope. Check if NSColor is already imported at the top of `_render_library_section` or imported inline. If not present, add an inline import at the top of the method body:

```python
        from AppKit import NSColor  # type: ignore[import-not-found]
```

(Place it next to the existing `import time` / `from bsky_saves_launcher import status as s` block at the top of `_render_library_section`.)

- [ ] **Step 2: Replace the in-flight detection block with three branches**

At popover.py:~1245, replace:

```python
        # In-flight detection: trust the GUI's current_state, which since
        # bsky-saves-gui v0.6.5-rc.4 reliably reflects all three hydration
        # stores throughout the hydration phase (R11 in the cross-repo
        # contract). No fallback inference needed at our dogfood scale.
        refreshing = snap.current_state == "refreshing"
        hydrating = snap.current_state == "hydrating"

        if refreshing:
            la_str = "Refreshing…"
        elif hydrating:
            la_str = "Backing up…"
        else:
            la_str = s.format_last_activity(snap)
        h["last_activity_label"].setStringValue_(la_str or "")
        h["last_activity_label"].setHidden_(la_str is None)
```

with:

```python
        # In-flight detection: trust the GUI's current_state, which since
        # bsky-saves-gui v0.6.5-rc.4 reliably reflects all three hydration
        # stores throughout the hydration phase (R11). The "error" branch
        # is panel-owned per R12 point 5: render the persisted refresh
        # error inline with red text + tooltip, sticky by construction
        # (we just render current_state — the helper persists "error" to
        # disk, so a launcher restart re-surfaces the same message).
        error = snap.current_state == "error"
        refreshing = snap.current_state == "refreshing"
        hydrating = snap.current_state == "hydrating"

        if error:
            err_msg = (
                snap.last_activity.errors[0].message
                if snap.last_activity and snap.last_activity.errors
                else ""
            )
            la_str = f"⚠ Refresh failed: {err_msg}" if err_msg else "⚠ Refresh failed"
        elif refreshing:
            la_str = "Refreshing…"
            err_msg = ""
        elif hydrating:
            la_str = "Backing up…"
            err_msg = ""
        else:
            la_str = s.format_last_activity(snap)
            err_msg = ""
        h["last_activity_label"].setStringValue_(la_str or "")
        h["last_activity_label"].setHidden_(la_str is None)
        try:
            h["last_activity_label"].setTextColor_(
                NSColor.systemRedColor() if error else NSColor.labelColor()
            )
            h["last_activity_label"].setToolTip_(err_msg)
        except Exception:
            pass
```

- [ ] **Step 3: Update the spinner block to use the new `error` variable**

The Task 2 block becomes:

```python
        spinning = refreshing or hydrating
        try:
            h["spinner"].setHidden_(not spinning)
            if spinning:
                h["spinner"].startAnimation_(None)
            else:
                h["spinner"].stopAnimation_(None)
        except Exception:
            pass
```

No change needed — `spinning` is already false when `error` is true since neither `refreshing` nor `hydrating` is set. Just verify by reading.

- [ ] **Step 4: Gate the errors badge on `not error`**

Replace the existing badge block at ~popover.py:1269:

```python
        # Errors badge: visible only when last_activity carries errors.
        errs = snap.last_activity.errors if snap.last_activity else []
        if errs:
            n = sum(e.count for e in errs)
            label = "error" if n == 1 else "errors"
            try:
                h["errors_badge_button"].setTitle_(f"{n} {label}")
                h["errors_badge_button"].setHidden_(False)
                tip = "\n".join(f"{e.kind}: {e.message} (×{e.count})" for e in errs)
                h["errors_badge_button"].setToolTip_(tip)
            except Exception:
                pass
        else:
            try:
                h["errors_badge_button"].setHidden_(True)
            except Exception:
                pass
```

with:

```python
        # Errors badge: visible only when last_activity carries errors
        # AND we're not already rendering the inline "Refresh failed"
        # message (R12) — otherwise the badge double-ups on the same
        # refresh_error entry.
        errs = snap.last_activity.errors if snap.last_activity else []
        if errs and not error:
            n = sum(e.count for e in errs)
            label = "error" if n == 1 else "errors"
            try:
                h["errors_badge_button"].setTitle_(f"{n} {label}")
                h["errors_badge_button"].setHidden_(False)
                tip = "\n".join(f"{e.kind}: {e.message} (×{e.count})" for e in errs)
                h["errors_badge_button"].setToolTip_(tip)
            except Exception:
                pass
        else:
            try:
                h["errors_badge_button"].setHidden_(True)
            except Exception:
                pass
```

- [ ] **Step 5: Verify lint and tests still pass**

Run: `uv run ruff check src/ tests/ && uv run --extra dev pytest tests/ -q`

Expected: lint clean, all tests pass. No new unit tests added (the R12 branch lives in AppKit-coupled `_render_library_section`, which has no existing test coverage; same situation as the `Refreshing…` / `Backing up…` branches).

- [ ] **Step 6: Commit**

```bash
git add src/bsky_saves_launcher/popover.py
git commit -m "Render current_state == 'error' inline (R12)

When the helper reports current_state='error', show '⚠ Refresh
failed: <message>' in the last-activity row (red, truncated, tooltip
carries full message). Hide the errors badge in this case so we
don't double-up on the same refresh_error entry. Hydration bars and
totals stay visible — last-known state remains useful context.

Sticky by construction: we just render current_state, so the helper's
persisted error survives launcher restarts and re-surfaces on next
poll (R12 points 2 + 3, satisfied without a client-side timer).

No retry button — Local GUI is the existing action surface. The
panel stays read-only.

Spec: docs/superpowers/specs/2026-05-22-r12-error-surface-design.md
Contract: bsky-saves-coordination R12."
```

---

### Task 4: Push branch

- [ ] **Step 1: Push**

```bash
git push origin claude/spec-installer-status-panel
```

Expected: three new commits land on the remote.

---

## Self-Review

**Spec coverage:**
- Inline `⚠ Refresh failed: <message>` in red — Task 3 step 2 ✓
- Tooltip with full message — Task 3 step 2 ✓
- Badge hidden when `error` — Task 3 step 4 ✓
- Spinner stopped + hidden — Task 2 + verified in Task 3 step 3 ✓
- Handle/totals/hydration stay visible — no code change needed (we only changed the la_str + badge + spinner, not the totals/hydration blocks) ✓
- No retry button — nothing to add ✓
- Sticky / restart-resurface — satisfied by construction (no client-side timer added) ✓
- Label truncation + max width — Task 1 ✓
- No new unit tests — explicit in plan ✓

**Placeholder scan:** No TBDs, TODOs, or "implement later". All code blocks are complete.

**Type consistency:** `error` (bool) and `err_msg` (str) introduced together in Task 3 step 2, referenced in steps 3 and 4. `spinning` introduced in Task 2, reused in Task 3 step 3. NSColor API: `systemRedColor()` and `labelColor()` are both AppKit class methods returning NSColor instances — both supported via PyObjC. `constraintLessThanOrEqualToAnchor_constant_` spelling matches the existing `constraintEqualToAnchor_` calls elsewhere in the file with the suffix variant for constants.

**Risk note:** The `library_content.widthAnchor()` constraint added in Task 1 references `library_content` which is in the same `_build_default_view` scope — no scope-leak issue. If `widthAnchor()` raises (it shouldn't on macOS 10.11+), the try/except falls through and the label keeps its intrinsic width (the previous behavior).
