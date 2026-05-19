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


def _build_default_view(ak, on_open_gui, on_copy_token, on_show_more, targets_out: list):
    """Build the Default view's NSView tree and return the root + handles.

    Returns (root_view, status_label, copy_button, copy_button_default_title).

    targets_out: caller-owned list. Every _PyCallbackTarget instance we create
    is appended here so the caller retains a strong reference. Without this,
    Python releases the target the moment setTarget_ returns and the button's
    action becomes a no-op (NSButton doesn't retain its target).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSFont,
        NSStackView,
        NSStackViewDistributionFill,
        NSTextField,
        NSUserInterfaceLayoutOrientationVertical,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(8.0)
    # Tight top inset so the status line sits near the top of the panel.
    stack.setEdgeInsets_((6, 12, 12, 12))  # T L B R

    status_label = NSTextField.labelWithString_("●  Loading…")
    status_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    stack.addArrangedSubview_(status_label)

    open_gui_button = NSButton.buttonWithTitle_target_action_(
        "Open GUI",
        None,
        None,
    )
    open_gui_button.setBezelStyle_(1)
    open_gui_target = _PyCallbackTarget.alloc().initWithCallable_(on_open_gui)
    targets_out.append(open_gui_target)
    open_gui_button.setTarget_(open_gui_target)
    open_gui_button.setAction_("invoke:")
    stack.addArrangedSubview_(open_gui_button)

    copy_button = NSButton.buttonWithTitle_target_action_(
        "Copy pairing token",
        None,
        None,
    )
    copy_button_default_title = "Copy pairing token"
    copy_button.setBezelStyle_(1)  # NSBezelStyleRounded
    copy_target = _PyCallbackTarget.alloc().initWithCallable_(on_copy_token)
    targets_out.append(copy_target)
    copy_button.setTarget_(copy_target)
    copy_button.setAction_("invoke:")
    stack.addArrangedSubview_(copy_button)

    more_button = NSButton.buttonWithTitle_target_action_(
        "More…",
        None,
        None,
    )
    more_button.setBezelStyle_(1)
    more_target = _PyCallbackTarget.alloc().initWithCallable_(on_show_more)
    targets_out.append(more_target)
    more_button.setTarget_(more_target)
    more_button.setAction_("invoke:")
    stack.addArrangedSubview_(more_button)

    stack.setFrame_(((0, 0), (260, 160)))

    return stack, status_label, copy_button, copy_button_default_title


def _build_more_view(
    ak,
    *,
    initial_start_at_login: bool,
    on_start_at_login_toggle,
    on_quit,
    on_back,
    targets_out: list,
):
    """Build the More panel's NSView tree.

    Returns (root_view, start_at_login_switch, version_label).
    targets_out: see _build_default_view docstring.

    Note: Show-in-Dock was removed in v0.3.x — macOS's recent-apps Dock
    cache made the toggle unreliable (clicking the leftover Dock entry
    revived the policy under the user). The launcher is now hardcoded
    menu-bar-only via LSUIElement=true + setActivationPolicy_(Accessory).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSFont,
        NSStackView,
        NSStackViewDistributionFill,
        NSSwitch,
        NSTextAlignmentCenter,
        NSTextField,
        NSUserInterfaceLayoutOrientationVertical,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(8.0)
    stack.setEdgeInsets_((12, 12, 12, 12))

    # Back arrow / title row
    back_button = NSButton.buttonWithTitle_target_action_("← Back", None, None)
    back_button.setBezelStyle_(1)
    back_target = _PyCallbackTarget.alloc().initWithCallable_(on_back)
    targets_out.append(back_target)
    back_button.setTarget_(back_target)
    back_button.setAction_("invoke:")
    stack.addArrangedSubview_(back_button)

    # Start at login toggle
    start_at_login_label = NSTextField.labelWithString_("Start at login")
    stack.addArrangedSubview_(start_at_login_label)
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
    stack.addArrangedSubview_(start_at_login_switch)

    # Quit
    quit_button = NSButton.buttonWithTitle_target_action_("Quit", None, None)
    quit_button.setBezelStyle_(1)
    quit_target = _PyCallbackTarget.alloc().initWithCallable_(on_quit)
    targets_out.append(quit_target)
    quit_button.setTarget_(quit_target)
    quit_button.setAction_("invoke:")
    stack.addArrangedSubview_(quit_button)

    # Add visible breathing room between Quit and the version footer.
    # setCustomSpacing_afterView_ overrides the default 8pt stack spacing
    # for just this gap.
    try:
        stack.setCustomSpacing_afterView_(20.0, quit_button)
    except Exception:
        pass

    # Version footer — two lines, small font, centered:
    #   bsky-saves <ver>
    #   GUI <ver> · Installer <ver>
    version_label = NSTextField.labelWithString_("…")
    version_label.setFont_(NSFont.systemFontOfSize_(NSFont.smallSystemFontSize()))
    version_label.setUsesSingleLineMode_(False)
    version_label.setMaximumNumberOfLines_(2)
    version_label.setAlignment_(NSTextAlignmentCenter)
    stack.addArrangedSubview_(version_label)

    stack.setFrame_(((0, 0), (260, 220)))

    return stack, start_at_login_switch, version_label


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

    def __init__(self, supervisor: Supervisor, tray_icon_ref) -> None:
        """tray_icon_ref is the pystray.Icon — we need _status_item for anchor."""
        self._supervisor = supervisor
        self._tray_icon_ref = tray_icon_ref
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

    def notify_helper_started(self) -> None:
        """Called by app.main() when supervisor.start() runs."""
        import time

        self._helper_started = time.monotonic()

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
            self._popover.showRelativeToRect_ofView_preferredEdge_(
                button.bounds(),
                button,
                ak["NSRectEdgeMinY"],  # popover hangs below the menu-bar button
            )
            # Keep the menu-bar button visually pressed while the popover is
            # open. NSStatusBarButton resets its highlight at mouseUp on the
            # same click that triggered our action, so any setHighlighted_
            # we call synchronously gets undone the moment this function
            # returns. Schedule on the next run-loop turn via NSTimer.
            self._tray_button = button

            def _apply_highlight(_t):
                try:
                    button.setHighlighted_(True)
                    cell = button.cell()
                    if cell is not None:
                        cell.setHighlighted_(True)
                    button.setNeedsDisplay_(True)
                except Exception as exc:
                    print(f"[popover] highlight failed: {exc!r}", file=sys.stderr)

            try:
                ak["NSTimer"].scheduledTimerWithTimeInterval_repeats_block_(
                    0.05, False, _apply_highlight
                )
            except Exception:
                pass
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

        default_root, status_label, copy_button, copy_default_title = _build_default_view(
            ak,
            on_open_gui=self._on_open_gui,
            on_copy_token=self._on_copy_token,
            on_show_more=self._on_show_more,
            targets_out=self._button_targets,
        )
        more_root, start_switch, version_label = _build_more_view(
            ak,
            initial_start_at_login=prefs.start_at_login,
            on_start_at_login_toggle=self._on_start_at_login_toggle,
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

        self._default_view = default_root
        self._more_view = more_root
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
        self._default_controller = default_controller
        self._more_controller = more_controller
        self._content_controller = default_controller

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
        """Swap to the More panel's view controller."""
        if self._popover is None or self._more_controller is None:
            return
        self._popover.setContentViewController_(self._more_controller)
        self._content_controller = self._more_controller

    def _on_back_to_default(self) -> None:
        """Swap back to the Default panel's view controller."""
        if self._popover is None or self._default_controller is None:
            return
        self._popover.setContentViewController_(self._default_controller)
        self._content_controller = self._default_controller

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

    def _on_popover_did_close(self) -> None:
        """NSPopoverDelegate hook — fires after the popover finishes closing."""
        self._stop_refresh_timer()
        if self._tray_button is not None:
            try:
                cell = self._tray_button.cell()
                if cell is not None:
                    cell.setHighlighted_(False)
                self._tray_button.setNeedsDisplay_(True)
            except Exception:
                pass

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

        counts = {"vev": 0, "views": 0}

        def walk(v):
            if v is None:
                return
            counts["views"] += 1
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
                counts["vev"] += 1
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
        print(
            f"[popover] frame-pin walked {counts['views']} views, "
            f"pinned {counts['vev']} NSVisualEffectView(s)",
            file=sys.stderr,
        )
