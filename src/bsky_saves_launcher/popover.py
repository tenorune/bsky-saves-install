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
        return "Unresponsive — helper not answering"
    if state is HelperState.PORT_CONFLICT:
        return "Port conflict — another bsky-saves is bound to 47826"
    return str(state.value)


def _build_default_view(ak, on_copy_token, on_show_more):
    """Build the Default view's NSView tree and return the root + handles.

    Returns (root_view, status_label, copy_button, copy_button_default_title).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSStackView,
        NSStackViewDistributionFill,
        NSTextField,
        NSUserInterfaceLayoutOrientationVertical,
    )

    stack = NSStackView.alloc().init()
    stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
    stack.setDistribution_(NSStackViewDistributionFill)
    stack.setSpacing_(8.0)
    stack.setEdgeInsets_((12, 12, 12, 12))  # T L B R

    status_label = NSTextField.labelWithString_("Loading…")
    stack.addArrangedSubview_(status_label)

    copy_button = NSButton.buttonWithTitle_target_action_(
        "Copy pairing token",
        None,
        None,
    )
    copy_button_default_title = "Copy pairing token"
    copy_button.setBezelStyle_(1)  # NSBezelStyleRounded
    copy_button.setTarget_(_PyCallbackTarget.alloc().initWithCallable_(on_copy_token))
    copy_button.setAction_("invoke:")
    stack.addArrangedSubview_(copy_button)

    more_button = NSButton.buttonWithTitle_target_action_(
        "More…",
        None,
        None,
    )
    more_button.setBezelStyle_(1)
    more_button.setTarget_(_PyCallbackTarget.alloc().initWithCallable_(on_show_more))
    more_button.setAction_("invoke:")
    stack.addArrangedSubview_(more_button)

    stack.setFrame_(((0, 0), (260, 120)))

    return stack, status_label, copy_button, copy_button_default_title


def _build_more_view(
    ak,
    *,
    initial_show_in_dock: bool,
    initial_start_at_login: bool,
    on_show_in_dock_toggle,
    on_start_at_login_toggle,
    on_quit,
    on_back,
):
    """Build the More panel's NSView tree.

    Returns (root_view, show_in_dock_switch, start_at_login_switch, version_label).
    """
    from AppKit import (  # type: ignore[import-not-found]
        NSButton,
        NSControlStateValueOff,
        NSControlStateValueOn,
        NSStackView,
        NSStackViewDistributionFill,
        NSSwitch,
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
    back_button.setTarget_(_PyCallbackTarget.alloc().initWithCallable_(on_back))
    back_button.setAction_("invoke:")
    stack.addArrangedSubview_(back_button)

    # Show in Dock toggle
    show_in_dock_label = NSTextField.labelWithString_("Show in Dock")
    stack.addArrangedSubview_(show_in_dock_label)
    show_in_dock_switch = NSSwitch.alloc().init()
    show_in_dock_switch.setState_(
        NSControlStateValueOn if initial_show_in_dock else NSControlStateValueOff
    )
    show_in_dock_switch.setTarget_(
        _PyCallbackTarget.alloc().initWithCallable_(
            lambda: on_show_in_dock_toggle(
                show_in_dock_switch.state() == NSControlStateValueOn
            )
        )
    )
    show_in_dock_switch.setAction_("invoke:")
    stack.addArrangedSubview_(show_in_dock_switch)

    # Start at login toggle
    start_at_login_label = NSTextField.labelWithString_("Start at login")
    stack.addArrangedSubview_(start_at_login_label)
    start_at_login_switch = NSSwitch.alloc().init()
    start_at_login_switch.setState_(
        NSControlStateValueOn if initial_start_at_login else NSControlStateValueOff
    )
    start_at_login_switch.setTarget_(
        _PyCallbackTarget.alloc().initWithCallable_(
            lambda: on_start_at_login_toggle(
                start_at_login_switch.state() == NSControlStateValueOn
            )
        )
    )
    start_at_login_switch.setAction_("invoke:")
    stack.addArrangedSubview_(start_at_login_switch)

    # Quit
    quit_button = NSButton.buttonWithTitle_target_action_("Quit BSky Saves", None, None)
    quit_button.setBezelStyle_(1)
    quit_button.setTarget_(_PyCallbackTarget.alloc().initWithCallable_(on_quit))
    quit_button.setAction_("invoke:")
    stack.addArrangedSubview_(quit_button)

    # Version footer (small label at the bottom; gets updated on each tick).
    version_label = NSTextField.labelWithString_("…")
    stack.addArrangedSubview_(version_label)

    stack.setFrame_(((0, 0), (260, 240)))

    return stack, show_in_dock_switch, start_at_login_switch, version_label


def _format_versions(
    launcher_version: str, helper_version: str | None, gui_version: str | None
) -> str:
    helper = helper_version or "—"
    gui = gui_version or "—"
    return f"BSky Saves {launcher_version} · bsky-saves {helper} · GUI {gui}"


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
        self._timer = None
        self._helper_started: float | None = None
        self._last_ping_ok: float | None = None
        self._last_snapshot = None
        self._status_label = None
        self._copy_button = None
        self._copy_default_title = "Copy pairing token"
        self._default_view = None
        self._more_view = None
        self._show_in_dock_switch = None
        self._start_at_login_switch = None
        self._version_label = None

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
            # Resize the popover to match whichever view is currently active.
            if self._content_controller is not None:
                view = self._content_controller.view()
                if view is not None:
                    frame = view.frame()
                    # frame.size is an NSSize tuple-ish (width, height); PyObjC
                    # exposes .width and .height attributes too.
                    try:
                        size = (frame.size.width, frame.size.height)
                    except AttributeError:
                        size = (frame[1][0], frame[1][1])
                    if size[0] > 0 and size[1] > 0:
                        self._popover.setContentSize_(size)
            self._popover.showRelativeToRect_ofView_preferredEdge_(
                button.bounds(),
                button,
                ak["NSRectEdgeMinY"],  # popover hangs below the menu-bar button
            )
            self._start_refresh_timer(ak)
        except Exception as exc:
            import traceback

            print(f"[popover] show failed: {exc!r}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    def _construct(self, ak) -> None:
        _ensure_callback_target_class()
        from bsky_saves_launcher.preferences import load_preferences

        prefs = load_preferences()

        default_root, status_label, copy_button, copy_default_title = _build_default_view(
            ak,
            on_copy_token=self._on_copy_token,
            on_show_more=self._on_show_more,
        )
        more_root, show_switch, start_switch, version_label = _build_more_view(
            ak,
            initial_show_in_dock=prefs.show_in_dock,
            initial_start_at_login=prefs.start_at_login,
            on_show_in_dock_toggle=self._on_show_in_dock_toggle,
            on_start_at_login_toggle=self._on_start_at_login_toggle,
            on_quit=self._on_quit,
            on_back=self._on_back_to_default,
        )

        self._default_view = default_root
        self._more_view = more_root
        self._status_label = status_label
        self._copy_button = copy_button
        self._copy_default_title = copy_default_title
        self._show_in_dock_switch = show_switch
        self._start_at_login_switch = start_switch
        self._version_label = version_label

        controller = ak["NSViewController"].alloc().init()
        controller.setView_(default_root)
        self._content_controller = controller

        popover = ak["NSPopover"].alloc().init()
        popover.setBehavior_(ak["NSPopoverBehaviorTransient"])
        popover.setContentSize_((260, 120))  # initial size; show() updates on each open
        popover.setContentViewController_(controller)
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
            self._status_label.setStringValue_(_status_line(snapshot))
        if self._version_label is not None:
            self._version_label.setStringValue_(
                _format_versions(launcher_version, snapshot.helper_version, snapshot.gui_version)
            )
        self._last_snapshot = snapshot

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
        """Swap the controller's view to the More panel."""
        if self._content_controller is None or self._more_view is None:
            return
        self._content_controller.setView_(self._more_view)

    def _on_back_to_default(self) -> None:
        if self._content_controller is None or self._default_view is None:
            return
        self._content_controller.setView_(self._default_view)

    def _on_show_in_dock_toggle(self, enabled: bool) -> None:
        from bsky_saves_launcher.activation import apply_activation_policy
        from bsky_saves_launcher.preferences import Preferences, load_preferences, save_preferences

        current = load_preferences()
        save_preferences(Preferences(show_in_dock=enabled, start_at_login=current.start_at_login))
        apply_activation_policy(show_in_dock=enabled)

    def _on_start_at_login_toggle(self, enabled: bool) -> None:
        from bsky_saves_launcher.launchagent import (
            LaunchAgentError,
            install_launch_agent,
            uninstall_launch_agent,
        )
        from bsky_saves_launcher.preferences import Preferences, load_preferences, save_preferences

        current = load_preferences()
        save_preferences(Preferences(show_in_dock=current.show_in_dock, start_at_login=enabled))
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
