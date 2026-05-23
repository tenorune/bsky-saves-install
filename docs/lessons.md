# Lessons learned

Hard-won facts about this codebase that aren't obvious from reading the code. Add an entry when a debugging session produces a non-trivial finding worth remembering for next time. Keep each entry self-contained: what was the symptom, what was the root cause, what's the rule.

## Layout: NSStackView GravityAreas is unreliable inside an NSPopover contentViewController swap

**Symptom.** Library content block inside the Default popover panel renders correctly on first open but drifts vertically on every More→Back navigation. Variants observed: bars pushed to bottom of panel (close to More link), library_content "inflated" past intrinsic content height, top-gravity children re-centering after a resize round-trip.

**Root cause.** When an `NSStackView` with `NSStackViewDistributionGravityAreas` is the content view of an `NSPopover` (wrapped in an `NSVisualEffectView` with autoresizing) and is re-set as the popover's contentView during a contentViewController swap + size tween, the gravity-zone leftover-space distribution does not behave deterministically. Required vertical `huggingPriority` on a top-gravity arranged subview is honored on first show but not after the swap. The exact mechanism is fuzzy — empirically the post-tween layout pass treats some gravity assignments differently than the first-layout pass — but the workaround is reliable.

**Rule.** Don't use GravityAreas distribution on a stack that will be swapped in/out of an `NSPopover.contentViewController` and resized via `preferredContentSize` tween. Instead:
- Use `NSStackViewDistributionFill`.
- Set required vertical content-hugging priority (1000) on every "real" arranged subview so they stay at intrinsic height.
- Insert a transparent `NSView` flex spacer between the top-anchored content and the bottom-anchored row (e.g. between library_content and a nav_row with a "More →" link), with low vertical hugging (250). The flex spacer absorbs all leftover height deterministically, which pins the bottom-anchored row to the bottom regardless of what the rest of the stack is doing.
- `setCustomSpacing_afterView_` is distribution-agnostic and still works.
- `setHidden_(True/False)` is what NSStackView observes for layout exclusion — not `setDisplayedWhenStopped_(False)`, which is purely visual and leaves the slot reserved.

**Fix landed in** `0c38654` on `claude/spec-installer-status-panel`.

**Related quirks worth remembering.**
- `NSTextField.setStringValue_` does NOT resolve intrinsic content size within the same runloop tick. Layout passes during that tick use stale (smaller) intrinsics — under required hugging this can collapse a container to a temporarily-wrong height. Wrap visibility toggles + string updates in `NSAnimationContext.beginGrouping` with `setDuration_(0.0)` + `setAllowsImplicitAnimation_(False)`, then call `layoutSubtreeIfNeeded()` synchronously to settle. See `ab57502`.
- `NSVisualEffectView` is layer-backed and propagates layer backing to descendants. Any frame change inside the VEV picks up Core Animation's default ~0.25s implicit duration — visible as a "slide" — unless suppressed via the above animation context.
- The VEV's inner stack autoresizing mask must include `NSViewHeightSizable` (not `NSViewMinYMargin`) so the inner tracks the VEV's size exactly across popover resizes. Without HeightSizable, post-resize drift offsets the entire content downward.
