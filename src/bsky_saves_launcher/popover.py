"""NSPopover host for the launcher status surface.

Two NSViewControllers (default view + More panel) live below; this module
owns the NSPopover, the navigation between the two views, and the 2 Hz
refresh timer that runs while the popover is visible.

Architecture:
    StatusPopover ── owns ──▶ NSPopover (delegate=self)
                         │
                         └─ contentViewController ──▶ NavController
                                                       │
                                                       ├─ DefaultViewController
                                                       └─ MoreViewController

On show():
    - Show the popover anchored to the tray icon's NSStatusItem button.
    - Start a 2 Hz timer that polls health.compute_health() and pushes
      the snapshot to whichever view is currently displayed.

On NSPopover close:
    - Stop the timer.
    - Reset nav state to the default view (so next show starts there).

NSPopoverBehaviorTransient — the popover dismisses on click-outside.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bsky_saves_launcher.status import StatusSnapshot
    from bsky_saves_launcher.supervisor import Supervisor


def _import_appkit():
    """Defer AppKit imports so the module imports on non-macOS for tests."""
    if sys.platform != "darwin":
        raise RuntimeError("StatusPopover requires macOS")
    from AppKit import (  # type: ignore[import-not-found]
        NSPopover,
        NSPopoverBehaviorTransient,
        NSRectEdgeMinY,
        NSViewController,
    )
    from Foundation import (  # type: ignore[import-not-found]
        NSObject,
        NSTimer,
    )
    return {
        "NSPopover": NSPopover,
        "NSPopoverBehaviorTransient": NSPopoverBehaviorTransient,
        "NSRectEdgeMinY": NSRectEdgeMinY,
        "NSViewController": NSViewController,
        "NSObject": NSObject,
        "NSTimer": NSTimer,
    }


def _format_uptime(seconds: float | None) -> str:
    """Human-readable uptime (e.g. '47 min', '3 h 12 min')."""
    if seconds is None or seconds < 1:
        return ""
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    h, rem = divmod(s, 3600)
    m = rem // 60
    return f"{h} h {m} min" if m else f"{h} h"


def _status_line(snapshot) -> str:
    """Human-facing single-line summary of the composite state."""
    from bsky_saves_launcher.health import HelperState

    state = snapshot.state
    uptime = _format_uptime(snapshot.uptime_seconds)
    if state is HelperState.RUNNING:
        return f"Running ({uptime})" if uptime else "Running"
    if state is HelperState.STARTING:
        return "Starting…"
    if state is HelperState.STOPPED:
        return "Stopped"
    if state is HelperState.UNRESPONSIVE:
        return "Helper not responding"
    if state is HelperState.PORT_CONFLICT:
        return "Another bsky-saves is using port 47826"
    return str(state.value)


def _status_dot_color(state):
    """NSColor for the status dot. Green when running, yellow while starting,
    red for any failure mode."""
    from AppKit import NSColor  # type: ignore[import-not-found]

    from bsky_saves_launcher.health import HelperState

    if state is HelperState.RUNNING:
        return NSColor.systemGreenColor()
    if state is HelperState.STARTING:
        return NSColor.systemYellowColor()
    return NSColor.systemRedColor()


def _build_status_attributed(snapshot):
    """Return an NSAttributedString with a colored '●' prefix + status text."""
    from AppKit import (  # type: ignore[import-not-found]
        NSForegroundColorAttributeName,
    )
    from Foundation import (  # type: ignore[import-not-found]
        NSMutableAttributedString,
    )

    text = f"●  {_status_line(snapshot)}"
    attr = NSMutableAttributedString.alloc().initWithString_(text)
    attr.addAttribute_value_range_(
        NSForegroundColorAttributeName,
        _status_dot_color(snapshot.state),
        (0, 1),
    )
    return attr


def _make_link_button(title: str, on_click, targets_out: list):
    """Create a borderless NSButton styled as a hyperlink.

    Visually distinct from the bezel-style action buttons so the user
    reads it as a navigation control, not an action. Uses the system
    `linkColor` at the regular system font size — no underline (cleaner
    look at larger size).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSColor,
        NSFont,
        NSForegroundColorAttributeName,
    )
    from Foundation import (  # type: ignore[import-not-found]
        NSMakeRange,
        NSMutableAttributedString,
    )

    btn = NSButton.buttonWithTitle_target_action_(title, None, None)
    btn.setBordered_(False)
    btn.setFont_(NSFont.systemFontOfSize_(NSFont.systemFontSize()))
    attr = NSMutableAttributedString.alloc().initWithString_(title)
    full = NSMakeRange(0, len(title))
    attr.addAttribute_value_range_(NSForegroundColorAttributeName, NSColor.linkColor(), full)
    btn.setAttributedTitle_(attr)
    target = _PyCallbackTarget.alloc().initWithCallable_(on_click)
    targets_out.append(target)
    btn.setTarget_(target)
    btn.setAction_("invoke:")
    return btn


def _build_default_view(
    ak,
    on_open_local_gui,
    on_open_saves_site,
    on_show_library,
    on_show_more,
    targets_out: list,
):
    """Build the Default panel.

    Layout (top to bottom):
        Status (●  Running)
        [breathing room]
        Open BSky Saves (centered label)
        [Local GUI]   [saves.lightseed.net]
        Library → (link, left)  [<flex>]  More → (link, right)

    Returns (root_view, status_label, _unused_, _unused_, library_link) —
    keeps the leading-shape stable so the construct() caller's existing
    destructuring needs minimal change. The copy-token control moved to
    the More panel. `library_link` is exposed so the popover owner can
    re-style it via `_update_default_library_link` when snapshot state
    changes.
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSFont,
        NSStackView,
        NSStackViewDistributionFill,
        NSTextAlignmentCenter,
        NSTextField,
        NSUserInterfaceLayoutOrientationHorizontal,
        NSUserInterfaceLayoutOrientationVertical,
        NSView,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(8.0)
    stack.setEdgeInsets_((6, 12, 2, 12))  # tight bottom inset

    status_label = NSTextField.labelWithString_("●  Loading…")
    status_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    stack.addArrangedSubview_(status_label)

    # "BSky Saves" header, all bold, centered.
    open_header = NSTextField.labelWithString_("BSky Saves")
    open_header.setAlignment_(NSTextAlignmentCenter)
    bold_font = NSFont.boldSystemFontOfSize_(NSFont.systemFontSize())
    open_header.setFont_(bold_font)
    stack.addArrangedSubview_(open_header)

    # Local GUI and saves.lightseed.net — each on its own line.
    local_gui_button = NSButton.buttonWithTitle_target_action_("Local GUI", None, None)
    local_gui_button.setBezelStyle_(1)
    local_target = _PyCallbackTarget.alloc().initWithCallable_(on_open_local_gui)
    targets_out.append(local_target)
    local_gui_button.setTarget_(local_target)
    local_gui_button.setAction_("invoke:")
    stack.addArrangedSubview_(local_gui_button)

    saves_site_button = NSButton.buttonWithTitle_target_action_(
        "saves.lightseed.net", None, None
    )
    saves_site_button.setBezelStyle_(1)
    saves_target = _PyCallbackTarget.alloc().initWithCallable_(on_open_saves_site)
    targets_out.append(saves_target)
    saves_site_button.setTarget_(saves_target)
    saves_site_button.setAction_("invoke:")
    stack.addArrangedSubview_(saves_site_button)

    # More space between status and the header; tight space between
    # the bottom button and the More link.
    try:
        stack.setCustomSpacing_afterView_(20.0, status_label)
        stack.setCustomSpacing_afterView_(4.0, saves_site_button)
    except Exception:
        pass

    # Bottom row: "Library →" on the left, flex spacer, "More →" on the
    # right. Both are link-styled (borderless, linkColor) — distinct from
    # the bezel-style action buttons above so the user reads them as
    # navigation rather than actions.
    nav_row = NSStackView.alloc().init()
    nav_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    nav_row.setDistribution_(NSStackViewDistributionFill)
    nav_row.setSpacing_(0)
    library_link = _make_link_button("Library →", on_show_library, targets_out)
    nav_row.addArrangedSubview_(library_link)
    nav_row.addArrangedSubview_(NSView.alloc().init())  # flex spacer
    more_link = _make_link_button("More →", on_show_more, targets_out)
    nav_row.addArrangedSubview_(more_link)
    stack.addArrangedSubview_(nav_row)

    stack.setFrame_(((0, 0), (300, 180)))

    # 4th and 5th slots are legacy / future hooks; kept as None to preserve
    # the construct() caller's destructuring shape. `library_link` is the
    # new addition so the popover owner can re-style it (e.g. grey-out
    # when there's no library snapshot) via _update_default_library_link.
    return stack, status_label, None, None, library_link


def _build_library_view(ak, on_back, on_open_local_gui, targets_out: list):
    """Build the Library panel.

    Layout (top to bottom):
        ← Back  (link, top-left)
        ── content view (visible when snapshot is present) ──
            handle (bold)
            "last seen N min ago" (small, hidden if fresh)
            "1,247 saves" (slightly larger)
            "15 lost · 2 unsaved" (small; hidden if all zero / absent)
            "Hydration" (section header; hidden if no rows present)
            Articles ████░░ 973 / 1247
            Threads  ███░░░ 412 / 1247
            Images   ████░░ 856 / 1247
            "Fetch · 2 min ago · +3 / −0" [spinner] [errors badge]
        ── placeholder view (visible when snapshot is None / no handle) ──
            "No active library status yet." (bold, centered)
            "Open the BSky Saves GUI and let it sync once — it'll show up
             here." (small, centered, wraps)
            [ Open BSky Saves GUI ] button

    Returns (root_view, handles_dict). The handles dict carries every
    label, level indicator, spinner, button, and container the caller
    needs to update at runtime via `_render_library_panel`.
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSBezelStyleRounded,
        NSButton,
        NSControlSizeSmall,
        NSFont,
        NSLevelIndicator,
        NSLevelIndicatorStyleContinuousCapacity,
        NSProgressIndicator,
        NSProgressIndicatorStyleSpinning,
        NSStackView,
        NSStackViewDistributionFill,
        NSTextAlignmentCenter,
        NSTextField,
        NSUserInterfaceLayoutOrientationHorizontal,
        NSUserInterfaceLayoutOrientationVertical,
        NSView,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(6.0)
    stack.setEdgeInsets_((6, 12, 12, 12))

    # Top-left "← Back" link.
    back_row = NSStackView.alloc().init()
    back_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    back_row.setSpacing_(0)
    back_link = _make_link_button("← Back", on_back, targets_out)
    back_row.addArrangedSubview_(back_link)
    back_row.addArrangedSubview_(NSView.alloc().init())  # flex spacer
    stack.addArrangedSubview_(back_row)

    # --- content view (shown when snapshot has at least a handle) ---
    content = NSStackView.alloc().init()
    content.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    content.setDistribution_(NSStackViewDistributionFill)
    content.setSpacing_(4.0)

    handle_label = NSTextField.labelWithString_("")
    handle_label.setFont_(NSFont.boldSystemFontOfSize_(NSFont.systemFontSize()))
    content.addArrangedSubview_(handle_label)

    staleness_label = NSTextField.labelWithString_("")
    staleness_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    content.addArrangedSubview_(staleness_label)

    total_label = NSTextField.labelWithString_("")
    total_label.setFont_(NSFont.systemFontOfSize_(NSFont.systemFontSize() + 1))
    content.addArrangedSubview_(total_label)

    retention_label = NSTextField.labelWithString_("")
    retention_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    content.addArrangedSubview_(retention_label)

    # Hydration section header + three pre-built rows. Each row is
    # show/hidden per-snapshot in _render_library_panel based on which
    # features the payload included.
    hydration_section_label = NSTextField.labelWithString_("Hydration")
    hydration_section_label.setFont_(NSFont.systemFontOfSize_(NSFont.systemFontSize()))
    content.addArrangedSubview_(hydration_section_label)
    try:
        content.setCustomSpacing_afterView_(12.0, retention_label)
    except Exception:
        pass

    # list of (label_NSTextField, bar_NSLevelIndicator, ratio_NSTextField, row_NSStackView)
    hydration_rows = []
    for label_text in ("Articles", "Threads", "Images"):
        row = NSStackView.alloc().init()
        row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        row.setSpacing_(8.0)
        lab = NSTextField.labelWithString_(label_text)
        lab.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
        bar = NSLevelIndicator.alloc().init()
        try:
            bar.setLevelIndicatorStyle_(NSLevelIndicatorStyleContinuousCapacity)
        except Exception:
            pass
        ratio = NSTextField.labelWithString_("")
        ratio.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
        row.addArrangedSubview_(lab)
        row.addArrangedSubview_(bar)
        row.addArrangedSubview_(ratio)
        content.addArrangedSubview_(row)
        hydration_rows.append((lab, bar, ratio, row))

    # Last-activity row: text label + (optional) spinner + (optional)
    # errors badge button.
    la_row = NSStackView.alloc().init()
    la_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    la_row.setSpacing_(6.0)
    last_activity_label = NSTextField.labelWithString_("")
    last_activity_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    la_row.addArrangedSubview_(last_activity_label)
    spinner = NSProgressIndicator.alloc().init()
    try:
        spinner.setStyle_(NSProgressIndicatorStyleSpinning)
    except Exception:
        pass
    try:
        spinner.setControlSize_(NSControlSizeSmall)
    except Exception:
        pass
    spinner.setIndeterminate_(True)
    spinner.setDisplayedWhenStopped_(False)
    la_row.addArrangedSubview_(spinner)
    errors_badge_button = NSButton.buttonWithTitle_target_action_("", None, None)
    errors_badge_button.setBezelStyle_(NSBezelStyleRounded)
    errors_badge_button.setHidden_(True)
    la_row.addArrangedSubview_(errors_badge_button)
    content.addArrangedSubview_(la_row)
    try:
        # Space above the last-activity row so it sits separately from
        # the hydration bars.
        content.setCustomSpacing_afterView_(12.0, hydration_rows[-1][3])
    except Exception:
        pass

    stack.addArrangedSubview_(content)

    # --- placeholder view (shown when snapshot is None or has no handle) ---
    placeholder = NSStackView.alloc().init()
    placeholder.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    placeholder.setDistribution_(NSStackViewDistributionFill)
    placeholder.setSpacing_(8.0)
    placeholder.setEdgeInsets_((12, 12, 12, 12))

    headline = NSTextField.labelWithString_("No active library status yet.")
    headline.setFont_(NSFont.boldSystemFontOfSize_(NSFont.systemFontSize()))
    headline.setAlignment_(NSTextAlignmentCenter)
    body = NSTextField.labelWithString_(
        "Open the BSky Saves GUI and let it sync once — it'll show up here."
    )
    body.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    body.setAlignment_(NSTextAlignmentCenter)
    body.setUsesSingleLineMode_(False)
    body.setMaximumNumberOfLines_(2)
    open_gui_button = NSButton.buttonWithTitle_target_action_(
        "Open BSky Saves GUI", None, None
    )
    open_gui_button.setBezelStyle_(NSBezelStyleRounded)
    pl_target = _PyCallbackTarget.alloc().initWithCallable_(on_open_local_gui)
    targets_out.append(pl_target)
    open_gui_button.setTarget_(pl_target)
    open_gui_button.setAction_("invoke:")
    placeholder.addArrangedSubview_(headline)
    placeholder.addArrangedSubview_(body)
    placeholder.addArrangedSubview_(open_gui_button)
    placeholder.setHidden_(True)
    stack.addArrangedSubview_(placeholder)

    stack.setFrame_(((0, 0), (300, 300)))

    return stack, {
        "back_link": back_link,
        "handle_label": handle_label,
        "staleness_label": staleness_label,
        "total_label": total_label,
        "retention_label": retention_label,
        "hydration_section_label": hydration_section_label,
        "hydration_rows": hydration_rows,
        "last_activity_label": last_activity_label,
        "spinner": spinner,
        "errors_badge_button": errors_badge_button,
        "content": content,
        "placeholder": placeholder,
    }


def _build_more_view(
    ak,
    *,
    initial_start_at_login: bool,
    on_start_at_login_toggle,
    on_copy_token,
    on_quit,
    on_back,
    targets_out: list,
):
    """Build the More panel.

    Layout (top to bottom):
        ← Back (link, top-left)
        Pairing Token:  [Copy]
        ─── horizontal separator ───
        Start at login           [switch]
        [spacer]
        Quit button
        Version footer (two lines, centered)

    Returns (root_view, start_at_login_switch, version_label, copy_button,
    copy_button_default_title).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSBox,
        NSBoxSeparator,
        NSButton,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSFont,
        NSGridCellPlacementCenter,
        NSGridCellPlacementLeading,
        NSGridCellPlacementTrailing,
        NSGridView,
        NSLayoutAttributeTop,
        NSLayoutConstraintOrientationVertical,
        NSStackView,
        NSStackViewDistributionFill,
        NSSwitch,
        NSTextAlignmentCenter,
        NSTextField,
        NSUserInterfaceLayoutOrientationHorizontal,
        NSUserInterfaceLayoutOrientationVertical,
        NSView,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(8.0)
    stack.setEdgeInsets_((6, 12, 12, 12))

    # Back link, top-left (flex spacer on the right pushes it left).
    back_row = NSStackView.alloc().init()
    back_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    back_row.setSpacing_(0)
    back_link = _make_link_button("← Back", on_back, targets_out)
    back_row.addArrangedSubview_(back_link)
    back_spacer = NSView.alloc().init()
    back_row.addArrangedSubview_(back_spacer)
    stack.addArrangedSubview_(back_row)

    # Two-row, two-column table: labels in left column, controls in
    # right column. NSGridView gives us proper column alignment.
    pairing_label = NSTextField.labelWithString_("Pairing token")
    copy_button = NSButton.buttonWithTitle_target_action_("Copy", None, None)
    copy_button_default_title = "Copy"
    copy_button.setBezelStyle_(1)
    # Pin the Copy button to a width that accommodates its widest
    # transient title ("No token yet"). Without this, NSGridView's
    # right column resizes on each flash, shifting the whole grid.
    copy_button.setTranslatesAutoresizingMaskIntoConstraints_(False)
    copy_button.widthAnchor().constraintEqualToConstant_(110.0).setActive_(True)
    copy_target = _PyCallbackTarget.alloc().initWithCallable_(on_copy_token)
    targets_out.append(copy_target)
    copy_button.setTarget_(copy_target)
    copy_button.setAction_("invoke:")

    sal_label = NSTextField.labelWithString_("Start at login")
    start_at_login_switch = NSSwitch.alloc().init()
    start_at_login_switch.setState_(
        NSControlStateValueOn if initial_start_at_login else NSControlStateValueOff
    )
    start_at_login_target = _PyCallbackTarget.alloc().initWithCallable_(
        lambda: on_start_at_login_toggle(
            start_at_login_switch.state() == NSControlStateValueOn
        )
    )
    targets_out.append(start_at_login_target)
    start_at_login_switch.setTarget_(start_at_login_target)
    start_at_login_switch.setAction_("invoke:")

    grid = NSGridView.gridViewWithViews_(
        [
            [pairing_label, copy_button],
            [sal_label, start_at_login_switch],
        ]
    )
    grid.setRowSpacing_(8.0)
    grid.setColumnSpacing_(12.0)
    grid.columnAtIndex_(0).setXPlacement_(NSGridCellPlacementTrailing)
    grid.columnAtIndex_(1).setXPlacement_(NSGridCellPlacementLeading)
    # Vertically centre the cells in each row so the labels line up
    # with the centres of their controls (default is top-aligned).
    grid.rowAtIndex_(0).setYPlacement_(NSGridCellPlacementCenter)
    grid.rowAtIndex_(1).setYPlacement_(NSGridCellPlacementCenter)

    # Centre the grid in the panel via a horizontal stack with
    # equal-width flex spacers on both sides. Previous attempts
    # (addView:inGravity:Center; wrapper with topAnchor+bottomAnchor)
    # either snapped the grid to one edge or stretched its row heights
    # on the second visit when the panel was re-parented. Equal-width
    # spacers consistently centre the grid across all re-layouts.
    table_row = NSStackView.alloc().init()
    table_row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    table_row.setDistribution_(NSStackViewDistributionFill)
    table_row.setSpacing_(0)
    # Anchor grid to the top of whatever vertical space the outer stack
    # allocates to this row. Without this, on the second More-panel
    # visit the row got allocated extra height and the grid floated
    # down to the bottom, almost touching the separator.
    table_row.setAlignment_(NSLayoutAttributeTop)
    left_spacer = NSView.alloc().init()
    right_spacer = NSView.alloc().init()
    table_row.addArrangedSubview_(left_spacer)
    table_row.addArrangedSubview_(grid)
    table_row.addArrangedSubview_(right_spacer)
    left_spacer.widthAnchor().constraintEqualToAnchor_(
        right_spacer.widthAnchor()
    ).setActive_(True)
    # Tell the outer stack not to stretch this row vertically, plus
    # pin the row's height to the grid's height directly. Two layers
    # of defence against the occasional re-layout drift.
    table_row.setContentHuggingPriority_forOrientation_(
        1000, NSLayoutConstraintOrientationVertical
    )
    table_row.heightAnchor().constraintEqualToAnchor_(
        grid.heightAnchor()
    ).setActive_(True)
    stack.addArrangedSubview_(table_row)

    # Tighten the gap below "← Back" and give the grid more breathing
    # room above the separator. Moves the grid up in the panel.
    try:
        stack.setCustomSpacing_afterView_(6.0, back_row)
        stack.setCustomSpacing_afterView_(14.0, table_row)
    except Exception:
        pass

    # Horizontal separator after the table.
    separator = NSBox.alloc().init()
    separator.setBoxType_(NSBoxSeparator)
    separator.setFrame_(((0, 0), (236, 1)))
    stack.addArrangedSubview_(separator)

    # Breathing room between the separator and Quit.
    try:
        stack.setCustomSpacing_afterView_(20.0, separator)
    except Exception:
        pass

    quit_button = NSButton.buttonWithTitle_target_action_("Quit", None, None)
    quit_button.setBezelStyle_(1)
    quit_target = _PyCallbackTarget.alloc().initWithCallable_(on_quit)
    targets_out.append(quit_target)
    quit_button.setTarget_(quit_target)
    quit_button.setAction_("invoke:")
    stack.addArrangedSubview_(quit_button)

    try:
        stack.setCustomSpacing_afterView_(20.0, quit_button)
    except Exception:
        pass

    version_label = NSTextField.labelWithString_("…")
    version_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    version_label.setUsesSingleLineMode_(False)
    version_label.setMaximumNumberOfLines_(2)
    version_label.setAlignment_(NSTextAlignmentCenter)
    stack.addArrangedSubview_(version_label)

    stack.setFrame_(((0, 0), (260, 230)))

    return stack, start_at_login_switch, version_label, copy_button, copy_button_default_title


def _wrap_in_active_visual_effect(inner):
    """Return an NSVisualEffectView (popover material, state=active) wrapping `inner`.

    Sized to the inner view's frame; the inner is added as a subview at
    origin (0,0). Returning the VEV lets the NSPopover content controller
    treat it as the root view — its frame.size still drives setContentSize_
    in show(), so popover sizing logic is unchanged.

    Why: NSPopover's default material reflects the host window's key state,
    which produces a visible color/opacity shift the moment a control inside
    the popover takes focus. state=NSVisualEffectStateActive forces the
    appearance to stay locked to "active" regardless of window focus.
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSVisualEffectBlendingModeBehindWindow,
        NSVisualEffectMaterialPopover,
        NSVisualEffectStateActive,
        NSVisualEffectView,
    )

    frame = inner.frame()
    try:
        size = (frame.size.width, frame.size.height)
    except AttributeError:
        size = (frame[1][0], frame[1][1])

    vev = NSVisualEffectView.alloc().initWithFrame_(((0, 0), size))
    vev.setMaterial_(NSVisualEffectMaterialPopover)
    vev.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
    vev.setState_(NSVisualEffectStateActive)
    inner.setFrame_(((0, 0), size))
    # Anchor the inner stack to the top of the VEV. If the popover ever
    # renders us inside a window taller than our intrinsic size (e.g. a
    # resize-on-back didn't fully take effect), this keeps the content
    # pinned to the top rather than the bottom (Cocoa origin is
    # bottom-left, so without MinYMargin extra height shows as a gap
    # above the stack).
    NSViewWidthSizable = 2
    NSViewMinYMargin = 8
    inner.setAutoresizingMask_(NSViewWidthSizable | NSViewMinYMargin)
    vev.addSubview_(inner)
    return vev


def _view_size(view):
    """Return the (width, height) of an NSView's frame, or None on failure."""
    try:
        frame = view.frame()
        try:
            return (frame.size.width, frame.size.height)
        except AttributeError:
            return (frame[1][0], frame[1][1])
    except Exception:
        return None


def _format_versions(
    launcher_version: str, helper_version: str | None, gui_version: str | None
) -> str:
    """Two-line version footer.

    Line 1: bsky-saves <helper version>
    Line 2: GUI <gui version> · Installer <launcher version>
    """
    helper = helper_version or "—"
    gui = gui_version or "—"
    return f"bsky-saves {helper}\nGUI {gui} · Installer {launcher_version}"


def _build_callback_target_class():
    """Define the NSObject-derived button target class. Returns the class."""
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]

    class _PyCallbackTarget(NSObject):
        def initWithCallable_(self, callable_):
            # PyObjC requires super().init() (or objc.super(...).init()) here —
            # `NSObject.init(self)` passes self as an extra positional arg
            # which raises 'Need 0 arguments, got 1' because Cocoa's -init
            # takes no parameters; the receiver is implicit.
            self = objc.super(_PyCallbackTarget, self).init()
            if self is None:
                return None
            self._callable = callable_
            return self

        def invoke_(self, _sender):
            try:
                self._callable()
            except Exception:
                import sys
                import traceback

                print(f"[popover] callback failed: {self._callable!r}", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)

    return _PyCallbackTarget


_PyCallbackTarget = None  # lazy class, built on first popover construction


def _build_popover_delegate_class():
    """NSPopoverDelegate that notifies the StatusPopover owner on close.

    Built lazily so the AppKit import only happens on macOS.
    """
    import objc  # type: ignore[import-not-found]
    from Foundation import NSObject  # type: ignore[import-not-found]

    class _PopoverDelegate(NSObject):
        def initWithOwner_(self, owner):
            self = objc.super(_PopoverDelegate, self).init()
            if self is None:
                return None
            self._owner_ref = owner
            return self

        def popoverWillClose_(self, _notification):
            # Release the tray-button highlight as soon as close starts, so
            # the visual change is in sync with the user's click rather
            # than lagging until the close animation finishes.
            owner = getattr(self, "_owner_ref", None)
            if owner is not None:
                owner._on_popover_will_close()

        def popoverDidClose_(self, _notification):
            owner = getattr(self, "_owner_ref", None)
            if owner is not None:
                owner._on_popover_did_close()

    return _PopoverDelegate


def _ensure_callback_target_class() -> None:
    global _PyCallbackTarget
    if _PyCallbackTarget is None and sys.platform == "darwin":
        _PyCallbackTarget = _build_callback_target_class()


class StatusPopover:
    """Owns the popover and its lifecycle. Constructed lazily on first show."""

    def __init__(self, supervisor: Supervisor, tray_icon_ref, *, tray=None) -> None:
        """tray_icon_ref is the pystray.Icon — we need _status_item for anchor.
        tray is the TrayApp owning the icon — used to drive the Selected
        layer (independent of the system highlight, which doesn't always
        render visibly on Tahoe)."""
        self._supervisor = supervisor
        self._tray_icon_ref = tray_icon_ref
        self._tray = tray
        self._popover = None  # NSPopover; constructed on first show
        self._content_controller = None
        self._default_controller = None
        self._more_controller = None
        self._timer = None
        self._helper_started: float | None = None
        self._last_ping_ok: float | None = None
        self._last_snapshot = None
        self._status_label = None
        self._copy_button = None
        self._copy_default_title = "Copy pairing token"
        self._default_view = None
        self._more_view = None
        self._start_at_login_switch = None
        self._version_label = None
        self._tray_button = None
        self._popover_delegate = None
        # Library panel state (v0.4.0)
        self._library_controller = None
        self._library_view = None
        self._library_handles = None
        self._default_library_link = None
        self._last_status_snapshot: StatusSnapshot | None = None

    def notify_helper_started(self) -> None:
        """Called by app.main() when supervisor.start() runs."""
        import time

        self._helper_started = time.monotonic()

    def is_shown(self) -> bool:
        """True if the popover is currently visible."""
        if self._popover is None:
            return False
        try:
            return bool(self._popover.isShown())
        except Exception:
            return False

    def close(self) -> None:
        """Explicitly close the popover, firing the delegate's
        popoverWillClose_ → un-highlight chain."""
        if self._popover is None:
            return
        try:
            self._popover.performClose_(None)
        except Exception:
            pass

    def toggle(self) -> None:
        """Open if closed, close if open.

        On the close path, un-highlight the tray button synchronously
        before calling performClose_ — popoverWillClose_'s un-highlight
        may fire asynchronously on some macOS versions, leaving the
        button visibly "stuck on" between the toggle-click and the
        async willClose callback.
        """
        if self.is_shown():
            if self._tray_button is not None:
                try:
                    self._tray_button.setHighlighted_(False)
                    self._tray_button.setNeedsDisplay_(True)
                except Exception:
                    pass
            self.close()
        else:
            self.show()

    def show(self) -> None:
        """Show the popover anchored to the tray icon. Lazy-construct on first call."""
        if sys.platform != "darwin":
            return
        try:
            ak = _import_appkit()
            if self._popover is None:
                self._construct(ak)
            status_item = getattr(self._tray_icon_ref, "_status_item", None)
            if status_item is None:
                print(
                    "[popover] tray_icon._status_item is None — pystray hasn't initialized?",
                    file=sys.stderr,
                )
                return
            button = status_item.button()
            if button is None:
                print("[popover] status_item.button() is None", file=sys.stderr)
                return
            # Always start at the Default view. NSPopover keeps whichever
            # contentViewController was set across hide/show, so without
            # this reset the popover would re-open on the More panel after
            # the user navigated there in a previous round.
            if self._default_controller is not None:
                self._popover.setContentViewController_(self._default_controller)
                self._content_controller = self._default_controller
            # Activate our app before showing the popover. We're
            # LSUIElement (background-only), so without this the app
            # never becomes "active" — and NSPopover.transient relies on
            # the app being active to detect click-outside and auto-
            # close. Without activate, the popover stays open after the
            # user clicks elsewhere.
            try:
                from AppKit import NSApp  # type: ignore[import-not-found]

                NSApp.activateIgnoringOtherApps_(True)
            except Exception:
                pass
            self._popover.showRelativeToRect_ofView_preferredEdge_(
                button.bounds(),
                button,
                ak["NSRectEdgeMinY"],  # popover hangs below the menu-bar button
            )
            # The tray's NSEvent local monitor already set the button's
            # highlight to True before delegating here. Because that
            # monitor consumes the mouseDown, the cell's tracking
            # cycle never runs and there's no auto-un-highlight on
            # mouseUp — so we don't need any NSTimer/observer re-apply
            # ceremony. Just record the button reference for the
            # popoverWillClose_ un-highlight.
            self._tray_button = button
            # Lock the popover window's appearance to the current system
            # appearance after show. Setting it on the popover alone wasn't
            # enough — NSPopover's private window also has its own appearance
            # property that needs pinning.
            try:
                from AppKit import NSApp  # type: ignore[import-not-found]

                effective = NSApp.effectiveAppearance()
                self._popover.setAppearance_(effective)
                controller = self._content_controller
                if controller is not None:
                    view = controller.view()
                    if view is not None:
                        window = view.window()
                        if window is not None:
                            window.setAppearance_(effective)
            except Exception as exc:
                print(f"[popover] appearance-pin failed: {exc!r}", file=sys.stderr)
            # Backup: walk the popover window's view tree and pin any
            # NSVisualEffectView to state=Active. Prints how many it found
            # so we can tell from logs whether the chrome VEV is reachable
            # via the standard view hierarchy.
            try:
                self._pin_popover_frame_active()
            except Exception as exc:
                print(f"[popover] frame-pin failed: {exc!r}", file=sys.stderr)
            self._start_refresh_timer(ak)
            # Immediate-on-show /status fetch. The tray's existing 5s
            # health tick takes over for subsequent refreshes while the
            # popover stays open (see TrayApp._on_health_tick).
            self._kick_status_fetch()
        except Exception as exc:
            import traceback

            print(f"[popover] show failed: {exc!r}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _construct(self, ak) -> None:
        _ensure_callback_target_class()
        from bsky_saves_launcher.preferences import load_preferences

        prefs = load_preferences()

        # NSButton.setTarget_ doesn't retain its target — keep strong refs
        # here so the action selectors stay live across button clicks.
        self._button_targets = []

        (
            default_root,
            status_label,
            _unused1,
            _unused2,
            default_library_link,
        ) = _build_default_view(
            ak,
            on_open_local_gui=self._on_open_gui,
            on_open_saves_site=self._on_open_saves_site,
            on_show_library=self._on_show_library,
            on_show_more=self._on_show_more,
            targets_out=self._button_targets,
        )
        self._default_library_link = default_library_link
        library_root, library_handles = _build_library_view(
            ak,
            on_back=self._on_back_to_default_from_library,
            on_open_local_gui=self._on_open_gui,
            targets_out=self._button_targets,
        )
        more_root, start_switch, version_label, copy_button, copy_default_title = _build_more_view(
            ak,
            initial_start_at_login=prefs.start_at_login,
            on_start_at_login_toggle=self._on_start_at_login_toggle,
            on_copy_token=self._on_copy_token,
            on_quit=self._on_quit,
            on_back=self._on_back_to_default,
            targets_out=self._button_targets,
        )

        # Wrap each root in an NSVisualEffectView locked to "active" state.
        # NSPopover otherwise renders its material with the host window's
        # key state, which causes a visible appearance shift the moment a
        # control inside the popover takes focus (e.g. when the user clicks
        # a button). state=Active pins the appearance regardless of focus.
        default_root = _wrap_in_active_visual_effect(default_root)
        more_root = _wrap_in_active_visual_effect(more_root)
        library_root = _wrap_in_active_visual_effect(library_root)

        self._default_view = default_root
        self._more_view = more_root
        self._library_view = library_root
        self._library_handles = library_handles
        self._status_label = status_label
        self._copy_button = copy_button
        self._copy_default_title = copy_default_title
        self._start_at_login_switch = start_switch
        self._version_label = version_label

        # Two separate NSViewControllers — one per panel. Each carries its
        # own preferredContentSize so NSPopover sizes itself correctly on
        # every swap. The previous single-controller-with-setView_ approach
        # left the popover stuck at whichever size the previous view had
        # because setContentSize_ on an already-shown popover doesn't
        # reliably shrink it on the macOS versions we target.
        default_controller = ak["NSViewController"].alloc().init()
        default_controller.setView_(default_root)
        default_size = _view_size(default_root)
        if default_size is not None:
            default_controller.setPreferredContentSize_(default_size)
        more_controller = ak["NSViewController"].alloc().init()
        more_controller.setView_(more_root)
        more_size = _view_size(more_root)
        if more_size is not None:
            more_controller.setPreferredContentSize_(more_size)
        library_controller = ak["NSViewController"].alloc().init()
        library_controller.setView_(library_root)
        library_size = _view_size(library_root)
        if library_size is not None:
            library_controller.setPreferredContentSize_(library_size)
        self._default_controller = default_controller
        self._more_controller = more_controller
        self._library_controller = library_controller
        self._content_controller = default_controller

        # Initial link styling: no snapshot yet → grey Library link.
        self._update_default_library_link()

        popover = ak["NSPopover"].alloc().init()
        popover.setBehavior_(ak["NSPopoverBehaviorTransient"])
        popover.setAnimates_(True)
        popover.setContentSize_(default_size or (260, 120))
        popover.setContentViewController_(default_controller)
        # Hide the popover's arrow. NSPopover doesn't expose a public API
        # for this, but the private KVC key `shouldHideAnchor` is honored
        # by AppKit and is the standard trick used in menu-bar apps that
        # want a flat popover. Wrapped in try/except — if Apple ever drops
        # the key, the arrow comes back but nothing breaks.
        try:
            popover.setValue_forKey_(True, "shouldHideAnchor")
        except Exception as exc:
            print(f"[popover] shouldHideAnchor not honored: {exc!r}", file=sys.stderr)
        # Delegate handles popoverDidClose_ → un-highlight tray button + stop
        # refresh timer. Retain it on self; NSPopover doesn't retain delegate.
        self._popover_delegate = _build_popover_delegate_class().alloc().initWithOwner_(self)
        popover.setDelegate_(self._popover_delegate)
        self._popover = popover

    def _start_refresh_timer(self, ak) -> None:
        """Start the 2 Hz refresh timer that polls health."""
        if self._timer is not None:
            return  # already running
        timer = ak["NSTimer"].scheduledTimerWithTimeInterval_repeats_block_(
            0.5,
            True,
            lambda _t: self._on_tick(),
        )
        self._timer = timer

    def _on_tick(self) -> None:
        from bsky_saves_launcher import __version__ as launcher_version
        from bsky_saves_launcher.health import compute_health

        snapshot = compute_health(
            self._supervisor,
            last_ping_ok=self._last_ping_ok,
            helper_started=self._helper_started,
        )
        if snapshot.last_seen_ok is not None:
            self._last_ping_ok = snapshot.last_seen_ok
        if self._status_label is not None:
            self._status_label.setAttributedStringValue_(_build_status_attributed(snapshot))
        if self._version_label is not None:
            self._version_label.setStringValue_(
                _format_versions(launcher_version, snapshot.helper_version, snapshot.gui_version)
            )
        self._last_snapshot = snapshot

    def _on_open_gui(self) -> None:
        from bsky_saves_launcher.tray import _open_or_focus_gui

        _open_or_focus_gui()

    def _on_open_saves_site(self) -> None:
        import webbrowser

        webbrowser.open("https://saves.lightseed.net/")

    def _on_copy_token(self) -> None:
        from bsky_saves_launcher.clipboard import ClipboardError, copy_to_clipboard
        from bsky_saves_launcher.token import read_pairing_token

        token = read_pairing_token()
        if token is None:
            self._flash_copy_button_title("No token yet")
            return
        try:
            copy_to_clipboard(token)
        except ClipboardError:
            self._flash_copy_button_title("Copy failed")
            return
        self._flash_copy_button_title("Copied ✓")

    def _flash_copy_button_title(self, title: str, *, revert_after_s: float = 1.5) -> None:
        """Temporarily change the Copy button's title, then revert."""
        if self._copy_button is None:
            return
        self._copy_button.setTitle_(title)
        from AppKit import NSTimer  # type: ignore[import-not-found]

        def _revert(_t):
            if self._copy_button is not None:
                self._copy_button.setTitle_(self._copy_default_title)

        NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            revert_after_s,
            False,
            _revert,
        )

    def _on_show_more(self) -> None:
        """Swap to the More panel's view controller, animated."""
        if self._popover is None or self._more_controller is None:
            return
        self._animated_swap_controller(self._more_controller)
        self._content_controller = self._more_controller

    def _on_back_to_default(self) -> None:
        """Swap back to the Default panel's view controller, animated."""
        if self._popover is None or self._default_controller is None:
            return
        self._animated_swap_controller(self._default_controller)
        self._content_controller = self._default_controller

    def _on_show_library(self) -> None:
        """Swap to the Library panel's view controller, animated.

        Renders whatever the current cached snapshot says (placeholder
        if no snapshot yet; populated content otherwise).
        """
        if self._popover is None or self._library_controller is None:
            return
        self._animated_swap_controller(self._library_controller)
        self._content_controller = self._library_controller
        self._render_library_panel()

    def _on_back_to_default_from_library(self) -> None:
        """Swap back to the Default panel from the Library panel."""
        if self._popover is None or self._default_controller is None:
            return
        self._animated_swap_controller(self._default_controller)
        self._content_controller = self._default_controller

    def update_library(self, snapshot) -> None:
        """Update the cached library snapshot and re-render relevant UI.

        Callable from any thread that is the main thread (UI updates are
        not thread-safe). The tray's 5s health tick marshals to the main
        queue before calling this; popover's own _kick_status_fetch
        worker thread does the same via _on_status_fetched.

        Idempotent and safe to call before _construct has run — handles
        are checked before use. Updates both the Library panel (if it's
        the visible content) and the Default panel's "Library →" link
        styling.
        """
        self._last_status_snapshot = snapshot
        self._update_default_library_link()
        if self._library_handles is None:
            return
        if self._content_controller is self._library_controller:
            self._render_library_panel()

    def _render_library_panel(self) -> None:
        """Populate the Library panel from the cached snapshot.

        Shows the 404 placeholder when there's no snapshot or no
        identified library; otherwise hides the placeholder and renders
        the data rows, hiding any sub-row whose payload field is absent.
        """
        h = self._library_handles
        if h is None:
            return
        snap = self._last_status_snapshot

        if snap is None or snap.library is None or snap.library.handle is None:
            h["content"].setHidden_(True)
            h["placeholder"].setHidden_(False)
            return

        h["placeholder"].setHidden_(True)
        h["content"].setHidden_(False)

        from bsky_saves_launcher import status as s

        h["handle_label"].setStringValue_(snap.library.handle)

        staleness = s.format_staleness(snap)
        if staleness is None:
            h["staleness_label"].setStringValue_("")
            h["staleness_label"].setHidden_(True)
        else:
            h["staleness_label"].setStringValue_(staleness)
            h["staleness_label"].setHidden_(False)

        total = s.format_total_saves(snap)
        h["total_label"].setStringValue_(total or "")
        h["total_label"].setHidden_(total is None)

        retention = s.format_retention(snap)
        h["retention_label"].setStringValue_(retention or "")
        h["retention_label"].setHidden_(retention is None)

        rows_data = s.format_hydration_rows(snap)
        # Show hydration section header only if at least one feature is
        # present in the payload.
        h["hydration_section_label"].setHidden_(len(rows_data) == 0)
        # strict=True asserts the invariant that the pre-built row list
        # and the contract-locked feature-name list are both length 3.
        for (_lab, bar, ratio, row), name in zip(
            h["hydration_rows"], ["articles", "threads", "images"], strict=True
        ):
            match = next(
                ((lbl, c, t) for lbl, c, t in rows_data if lbl.lower() == name),
                None,
            )
            if match is None:
                row.setHidden_(True)
                continue
            _, completed, total_v = match
            row.setHidden_(False)
            try:
                bar.setMinValue_(0.0)
                bar.setMaxValue_(float(total_v) if total_v > 0 else 1.0)
                bar.setDoubleValue_(float(completed))
            except Exception:
                pass
            ratio.setStringValue_(f"{completed:,} / {total_v:,}")

        la_str = s.format_last_activity(snap)
        h["last_activity_label"].setStringValue_(la_str or "")
        h["last_activity_label"].setHidden_(la_str is None)

        # Spinner visibility tracks current_state in-flight states.
        try:
            if snap.current_state in ("refreshing", "hydrating"):
                h["spinner"].startAnimation_(None)
            else:
                h["spinner"].stopAnimation_(None)
        except Exception:
            pass

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

    def _update_default_library_link(self) -> None:
        """Style the Default panel's 'Library →' link based on whether
        the cached snapshot has a populated library. Greys the title
        (disabledControlTextColor) when there's nothing to render; uses
        the normal link color otherwise. The link remains clickable in
        both states — tapping a greyed link still navigates to the
        Library panel, which renders the 404 placeholder.
        """
        link = self._default_library_link
        if link is None:
            return
        snap = self._last_status_snapshot
        has_data = (
            snap is not None
            and snap.library is not None
            and snap.library.handle is not None
        )
        try:
            from AppKit import (  # type: ignore[import-not-found]
                NSColor,
                NSForegroundColorAttributeName,
            )
            from Foundation import (  # type: ignore[import-not-found]
                NSMakeRange,
                NSMutableAttributedString,
            )

            title = "Library →"
            attr = NSMutableAttributedString.alloc().initWithString_(title)
            color = NSColor.linkColor() if has_data else NSColor.disabledControlTextColor()
            attr.addAttribute_value_range_(
                NSForegroundColorAttributeName, color, NSMakeRange(0, len(title))
            )
            link.setAttributedTitle_(attr)
        except Exception:
            pass

    def _kick_status_fetch(self) -> None:
        """Immediate-on-show status fetch. Runs the blocking httpx call
        on a daemon worker thread and marshals the result back to the
        main thread via NSOperationQueue so the AppKit update happens
        on the main runloop."""
        import threading

        def worker():
            from bsky_saves_launcher import status as s
            from bsky_saves_launcher import token as t

            try:
                tok = t.read_pairing_token()
            except Exception:
                tok = None
            if not tok:
                snap = None
            else:
                try:
                    snap = s.fetch_status(token=tok)
                except Exception:
                    snap = None
            self._on_status_fetched(snap)

        threading.Thread(target=worker, daemon=True).start()

    def _on_status_fetched(self, snapshot) -> None:
        """Marshal a fetched snapshot back to the main thread for UI
        update. Called from background worker threads.

        If the main-queue dispatch itself fails, the update is dropped
        rather than fired from the worker thread — calling AppKit off
        the main thread is worse than missing one tick (the next tray
        health-poll cycle, ~5s later, will refresh the snapshot).
        """
        try:
            from Foundation import NSOperationQueue  # type: ignore[import-not-found]

            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: self.update_library(snapshot)
            )
        except Exception as exc:
            print(f"[popover] status update dispatch failed: {exc!r}", file=sys.stderr)

    def _animated_swap_controller(self, controller) -> None:
        """Swap the popover's contentViewController and animate the size
        change with a manual frame-stepped tween.

        Drive the new controller's preferredContentSize each frame —
        NSPopover observes that property and resizes its window. Calling
        popover.setContentSize_ directly was inconsistent on Tahoe; the
        preferredContentSize path is the documented one.
        """
        try:
            old_size = self._popover.contentSize()
            new_size = controller.preferredContentSize()
            try:
                old_w, old_h = old_size.width, old_size.height
            except AttributeError:
                old_w, old_h = old_size[0], old_size[1]
            try:
                new_w, new_h = new_size.width, new_size.height
            except AttributeError:
                new_w, new_h = new_size[0], new_size[1]
            # Snap content swap (no cross-fade flash). Force the new
            # controller's preferredContentSize to the OLD size so the
            # popover doesn't snap to new_size before we can tween.
            try:
                controller.setPreferredContentSize_((old_w, old_h))
            except Exception:
                pass
            self._popover.setAnimates_(False)
            self._popover.setContentViewController_(controller)
            self._popover.setAnimates_(True)

            self._start_size_tween(controller, old_w, old_h, new_w, new_h, duration_s=0.083)
        except Exception as exc:
            print(f"[popover] animated swap failed: {exc!r}", file=sys.stderr)
            import traceback

            traceback.print_exc(file=sys.stderr)
            try:
                self._popover.setContentViewController_(controller)
            except Exception:
                pass

    def _start_size_tween(self, controller, ow, oh, nw, nh, *, duration_s: float) -> None:
        """Drive controller.preferredContentSize from (ow, oh) to (nw, nh)."""
        import math

        from Foundation import (  # type: ignore[import-not-found]
            NSRunLoop,
            NSRunLoopCommonModes,
            NSTimer,
        )

        # Cancel any in-flight tween so back-to-back swaps don't fight.
        existing = getattr(self, "_size_tween_timer", None)
        if existing is not None:
            try:
                existing.invalidate()
            except Exception:
                pass
            self._size_tween_timer = None

        fps = 60.0
        n_steps = max(1, int(round(duration_s * fps)))
        interval = duration_s / n_steps
        state = {"i": 0}

        def tick(t):
            state["i"] += 1
            progress = min(1.0, state["i"] / n_steps)
            eased = 0.5 * (1.0 - math.cos(progress * math.pi))
            cw = ow + (nw - ow) * eased
            ch = oh + (nh - oh) * eased
            try:
                controller.setPreferredContentSize_((cw, ch))
            except Exception as exc:
                print(f"[popover] tween tick failed: {exc!r}", file=sys.stderr)
                try:
                    t.invalidate()
                except Exception:
                    pass
                return
            if state["i"] >= n_steps:
                try:
                    t.invalidate()
                except Exception:
                    pass
                self._size_tween_timer = None

        timer = NSTimer.timerWithTimeInterval_repeats_block_(interval, True, tick)
        NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
        self._size_tween_timer = timer

    def _on_start_at_login_toggle(self, enabled: bool) -> None:
        from bsky_saves_launcher.launchagent import (
            LaunchAgentError,
            install_launch_agent,
            uninstall_launch_agent,
        )
        from bsky_saves_launcher.preferences import Preferences, save_preferences

        save_preferences(Preferences(start_at_login=enabled))
        try:
            if enabled:
                install_launch_agent(app_path="/Applications/BSky Saves.app")
            else:
                uninstall_launch_agent()
        except LaunchAgentError:
            # Best-effort: the preference is the source of truth; UI revert
            # is handled by the popover's next refresh tick (Task 6).
            pass

    def _on_quit(self) -> None:
        import os

        os._exit(0)

    def _stop_refresh_timer(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def _on_popover_will_close(self) -> None:
        """NSPopoverDelegate hook — fires at the start of the close.

        Un-highlight the tray button immediately so the pressed-state
        release lands at the start of the close animation, not after it.
        """
        if self._tray_button is not None:
            try:
                self._tray_button.setHighlighted_(False)
                cell = self._tray_button.cell()
                if cell is not None:
                    cell.setHighlighted_(False)
                self._tray_button.setNeedsDisplay_(True)
            except Exception:
                pass

    def _on_popover_did_close(self) -> None:
        """NSPopoverDelegate hook — fires after the popover finishes closing."""
        self._stop_refresh_timer()

    def _pin_popover_frame_active(self) -> None:
        """Force the popover window's NSVisualEffectView(s) to state=Active.

        NSPopover's arrow + frame are drawn by a private NSVisualEffectView
        inside the popover's window. By default that view's state tracks the
        window's key/active state, so clicking inside the popover (which
        moves focus) causes the arrow to flicker between active/inactive
        appearances. Walk the popover's window view tree and pin every
        NSVisualEffectView we find to state=Active.

        Uses class-name string matching (no private symbol imports), so
        this is safe-by-default: if Apple renames the private classes,
        we no-op rather than crash.
        """
        from AppKit import (  # type: ignore[import-not-found]
            NSVisualEffectStateActive,
            NSVisualEffectView,
        )

        controller = self._content_controller
        if controller is None:
            return
        view = controller.view()
        if view is None:
            return
        window = view.window()
        if window is None:
            return

        def walk(v):
            if v is None:
                return
            # isKindOfClass_ catches private NSVisualEffectView subclasses
            # that Python's isinstance can miss; respondsToSelector_ is the
            # duck-typed fallback if the class check is unexpectedly false.
            try:
                matches = v.isKindOfClass_(NSVisualEffectView) or v.respondsToSelector_(
                    "setState:"
                )
            except Exception:
                matches = False
            if matches:
                try:
                    v.setState_(NSVisualEffectStateActive)
                except Exception:
                    pass
            try:
                subs = v.subviews()
            except Exception:
                return
            for sub in subs:
                walk(sub)

        # Start from the window's content view's *parent* (the popover's
        # private frame view) so we sweep both frame and contentView trees.
        content = window.contentView()
        if content is None:
            return
        root = content.superview() or content
        walk(root)
