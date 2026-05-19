"""Menu-bar / system-tray icon for the launcher.

Renders a pystray icon, wires click-to-open-popover, and overlays a small
colored state badge in the icon's bottom-right corner (green/yellow/red
per HelperState — same color logic as the popover's status dot).
"""

from __future__ import annotations

import webbrowser
from collections.abc import Callable
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    import pystray

from bsky_saves_launcher.supervisor import Supervisor

LOCAL_GUI_URL = "http://127.0.0.1:47826/"
HEALTH_TICK_SECONDS = 5.0

# v0.1: each "Open GUI" click hands the URL to the default browser via
# webbrowser.open, which opens a new tab. An AppleScript variant that focuses
# an existing tab in Safari / Chrome was prototyped (see git history of this
# file, commit 020e7e8) and pulled because it requires per-browser Automation
# permission prompts. Revisit if the new-tab behavior bites.
#
# _FOCUS_OR_OPEN_APPLESCRIPT = r"""
# on run argv
#     set targetURL to item 1 of argv
#     tell application "System Events"
#         set runningApps to name of processes
#     end tell
#     if runningApps contains "Safari" then
#         try
#             tell application "Safari"
#                 repeat with w in windows
#                     repeat with t in tabs of w
#                         if URL of t starts with targetURL then
#                             set current tab of w to t
#                             set index of w to 1
#                             activate
#                             return
#                         end if
#                     end repeat
#                 end repeat
#             end tell
#         end try
#     end if
#     if runningApps contains "Google Chrome" then
#         try
#             tell application "Google Chrome"
#                 repeat with w in windows
#                     set tIndex to 0
#                     repeat with t in tabs of w
#                         set tIndex to tIndex + 1
#                         if URL of t starts with targetURL then
#                             set active tab index of w to tIndex
#                             set index of w to 1
#                             activate
#                             return
#                         end if
#                     end repeat
#                 end repeat
#             end tell
#         end try
#     end if
#     open location targetURL
# end run
# """


def _open_or_focus_gui() -> None:
    """Open LOCAL_GUI_URL in the default browser (new tab each call, v0.1)."""
    webbrowser.open(LOCAL_GUI_URL)


def _make_icon_image(*, running: bool) -> Image.Image:  # noqa: ARG001 (running unused in v0.2.0)
    """Load the bundled menu-bar silhouette.

    v0.2.0: a single template-image silhouette regardless of state. State
    indication via badge overlay is planned for a later release (see
    docs/superpowers/specs/2026-05-18-launcher-ux.md R3).
    """
    from pathlib import Path

    here = Path(__file__).resolve().parent
    path = here / "resources" / "menubar.png"
    return Image.open(path).convert("RGBA")


def _status_badge_color(state):
    """NSColor for the menu-bar badge dot. Only red is surfaced — green and
    yellow correspond to healthy / transient-starting and are hidden via
    _state_should_show_badge below. Lazy AppKit import so this module
    imports cleanly on non-macOS for tests."""
    from AppKit import NSColor  # type: ignore[import-not-found]

    return NSColor.systemRedColor()


def _state_should_show_badge(state) -> bool:
    """True when the menu-bar badge should be visible.

    Only failure-mode states surface a badge — RUNNING and STARTING don't
    draw user attention to the menu bar. STOPPED / UNRESPONSIVE /
    PORT_CONFLICT all warrant a red dot.
    """
    from bsky_saves_launcher.health import HelperState

    return state in {
        HelperState.STOPPED,
        HelperState.UNRESPONSIVE,
        HelperState.PORT_CONFLICT,
    }


class TrayApp:
    """Owns the pystray icon and dispatches its menu items."""

    def __init__(
        self,
        supervisor: Supervisor,
        *,
        on_open_status: Callable[[], None],
        helper_started: float | None = None,
    ) -> None:
        self._supervisor = supervisor
        self._on_open_status = on_open_status
        self._helper_started = helper_started
        self._last_ping_ok: float | None = None
        self._icon: pystray.Icon | None = None
        self._badge_layer = None
        self._health_timer = None
        self._click_target = None

    def run(self) -> None:
        """Block on the pystray event loop. Must be called on the main thread."""
        import pystray

        # No pystray menu — pystray's macOS backend forces left-click to
        # show the menu whenever one is attached (HAS_DEFAULT_ACTION=False
        # in pystray/_darwin.py, "We support only a default action with an
        # empty menu"). Left-click must open the popover, so we omit the
        # menu and wire the NSStatusItem button's action directly in
        # _on_pystray_ready. Quit lives in the popover.
        self._icon = pystray.Icon(
            name="bsky-saves",
            icon=_make_icon_image(running=self._supervisor.is_alive()),
            title="BSky Saves",
        )
        # `setup` runs after pystray's NSStatusItem is created (the constructor
        # only stashes our PIL image; the native item doesn't exist yet at
        # this point). Set the macOS template-image flag from inside the
        # callback so macOS handles light/dark/tinted adaptation.
        self._icon.run(setup=self._on_pystray_ready)

    def _on_pystray_ready(self, icon) -> None:  # noqa: ARG002 (icon == self._icon)
        """pystray setup callback — runs once the NSStatusItem is alive."""
        # Visible by default; pystray won't show the icon until we set this
        # OR call icon.run() with a positional `visible=True`. Setting it
        # explicitly here keeps the icon visible across any future
        # restart/refresh logic.
        if self._icon is not None:
            self._icon.visible = True
        self._flag_macos_template_image()
        self._install_click_action()
        self._configure_state_driven_button()
        self._install_badge_layer()
        self._start_health_timer()

    def _configure_state_driven_button(self) -> None:
        """Make the tray button's pressed look driven by state, not tracking.

        Default NSStatusBarButton behavior: mouseDown highlights the button,
        mouseUp un-highlights. That produces a flicker on the round-trip
        from click → popover open (system unhighlights at mouseUp, then we
        re-apply highlight a moment later for the Selected appearance).

        Re-wire the cell so tracking has no visual effect (highlightsBy=0)
        and visual appearance follows the button's state (showsStateBy=
        NSChangeBackgroundCellMask). The popover toggles state via
        set_selected(True/False) on show/close — no NSTimer, no blink.
        """
        import sys

        if sys.platform != "darwin" or self._icon is None:
            return
        try:
            from AppKit import (  # type: ignore[import-not-found]
                NSChangeBackgroundCellMask,
            )

            status_item = getattr(self._icon, "_status_item", None)
            if status_item is None:
                return
            button = status_item.button()
            if button is None:
                return
            cell = button.cell()
            if cell is None:
                return
            cell.setHighlightsBy_(0)
            cell.setShowsStateBy_(NSChangeBackgroundCellMask)
            button.setState_(0)  # NSControlStateValueOff = Unselected
        except Exception as exc:
            print(f"[tray] state-driven config failed: {exc!r}", file=sys.stderr)

    def set_selected(self, selected: bool) -> None:
        """Set the tray button's Selected/Unselected visual state."""
        import sys

        if sys.platform != "darwin" or self._icon is None:
            return
        try:
            status_item = getattr(self._icon, "_status_item", None)
            if status_item is None:
                return
            button = status_item.button()
            if button is None:
                return
            button.setState_(1 if selected else 0)
            button.setNeedsDisplay_(True)
        except Exception:
            pass

    def _install_click_action(self) -> None:
        """Wire the NSStatusItem button to open the popover on left-click.

        pystray sets its own button target/action in _darwin.Icon._create, but
        since we passed no menu, that wiring fires the icon's default-item
        callback (which doesn't exist for us). We override it here to call
        on_open_status directly. The button target NSObject must be retained
        on `self` — NSButton.setTarget_ doesn't retain its target, so without
        the strong ref Python would GC it and the action would no-op.
        """
        import sys

        if sys.platform != "darwin" or self._icon is None:
            return
        try:
            import objc  # type: ignore[import-not-found]  # noqa: F401
            from Foundation import NSObject  # type: ignore[import-not-found]

            on_open_status = self._on_open_status

            class _ClickTarget(NSObject):
                def invoke_(self, _sender):
                    try:
                        on_open_status()
                    except Exception as exc:
                        import traceback

                        print(f"[tray] popover open failed: {exc!r}", file=sys.stderr)
                        traceback.print_exc(file=sys.stderr)

            status_item = getattr(self._icon, "_status_item", None)
            if status_item is None:
                return
            target = _ClickTarget.alloc().init()
            self._click_target = target  # retain — see docstring
            button = status_item.button()
            button.setTarget_(target)
            button.setAction_("invoke:")
        except Exception as exc:
            print(f"[tray] _install_click_action failed: {exc!r}", file=sys.stderr)

    def _flag_macos_template_image(self) -> None:
        """Configure the menu-bar NSImage to match Apple's HIG.

        Two PyObjC tweaks to pystray's macOS NSImage:

        1. setTemplate_(YES) — tells macOS this is a template image, so it
           handles light/dark/tinted-mode adaptation automatically.
        2. setSize_((22, 22)) — sets the *logical* (point) size to match
           Apple's menu-bar template-image convention (Sonoma → Tahoe).
           pystray hands the raw PNG bytes to NSImage without setting a
           logical size, so NSImage defaults to the pixel size (88pt for
           our 88x88 PNG) — which renders much larger than neighboring
           system icons. The 88px pixel resolution remains as 4x retina
           detail behind the 22pt logical render.

        Must run AFTER pystray initializes the NSStatusItem (call from the
        setup= callback to Icon.run()); calling earlier silently no-ops
        because _status_item is still None.
        """
        import sys

        if sys.platform != "darwin" or self._icon is None:
            return
        try:
            status_item = getattr(self._icon, "_status_item", None)
            if status_item is None:
                return
            ns_image = status_item.button().image()
            if ns_image is not None:
                ns_image.setTemplate_(True)
                # PyObjC accepts a (w, h) tuple as an NSSize.
                ns_image.setSize_((22, 22))
        except Exception:
            # Patch is best-effort — if pystray's internals shifted, fall
            # back to the un-flagged image. The launcher still works; the
            # icon just doesn't auto-adapt to dark mode and may render at
            # the wrong size.
            pass

    def _install_badge_layer(self) -> None:
        """Add a small colored CALayer to the status button's corner.

        The silhouette stays a template image so macOS keeps adapting it
        to light/dark/tinted appearances. The badge is a separate layer
        drawn on top so it can carry color without losing the silhouette's
        adaptive rendering — template-image semantics force the underlying
        PNG to grayscale.
        """
        import sys

        if sys.platform != "darwin" or self._icon is None:
            return
        try:
            from AppKit import NSColor  # type: ignore[import-not-found]
            from Quartz import CAShapeLayer  # type: ignore[import-not-found]

            status_item = getattr(self._icon, "_status_item", None)
            if status_item is None:
                return
            button = status_item.button()
            if button is None:
                return
            button.setWantsLayer_(True)
            layer = CAShapeLayer.layer()
            # Position the 6pt dot at the bottom-right corner of the
            # button. NSStatusBarButton's layer uses flipped geometry
            # (origin top-left), so "bottom" means high Y. Read bounds
            # rather than hardcoding so we adapt to whatever width macOS
            # gives the status item (varies a few points by macOS
            # version / status-bar layout).
            bounds = button.bounds()
            try:
                bw, bh = bounds.size.width, bounds.size.height
            except AttributeError:
                bw, bh = bounds[1][0], bounds[1][1]
            badge_size = 6.0
            margin = 1.0
            # Pull the badge a bit more than a full badge-width into the icon
            # so it sits clearly over the silhouette rather than at the edge.
            overlap = badge_size + 2.0
            layer.setFrame_((
                (bw - badge_size - margin - overlap, bh - badge_size - margin),
                (badge_size, badge_size),
            ))
            layer.setCornerRadius_(badge_size / 2.0)
            layer.setBackgroundColor_(NSColor.systemRedColor().CGColor())
            layer.setHidden_(True)  # start hidden; tick reveals on red state
            button.layer().addSublayer_(layer)
            self._badge_layer = layer
        except Exception as exc:
            print(f"[tray] _install_badge_layer failed: {exc!r}", file=sys.stderr)

    def _start_health_timer(self) -> None:
        """Poll helper health every HEALTH_TICK_SECONDS to update the badge.

        Add the timer to the main run loop in NSRunLoopCommonModes so it
        fires regardless of which run-loop mode pystray's event pump is
        currently in. The plain scheduledTimer convenience installs into
        the default mode only, which is why a timer that ticked once at
        startup was never firing again under pystray's loop.
        """
        import sys

        if sys.platform != "darwin":
            return
        try:
            from Foundation import (  # type: ignore[import-not-found]
                NSRunLoop,
                NSRunLoopCommonModes,
                NSTimer,
            )

            timer = NSTimer.timerWithTimeInterval_repeats_block_(
                HEALTH_TICK_SECONDS,
                True,
                lambda _t: self._on_health_tick(),
            )
            NSRunLoop.mainRunLoop().addTimer_forMode_(timer, NSRunLoopCommonModes)
            self._health_timer = timer
            # Kick once immediately so we don't wait HEALTH_TICK_SECONDS to
            # learn the helper state on launch.
            self._on_health_tick()
        except Exception as exc:
            print(f"[tray] _start_health_timer failed: {exc!r}", file=sys.stderr)

    def _on_health_tick(self) -> None:
        """Compute health, toggle the badge, and auto-restart a dead helper.

        Only failure-mode states surface a (red) badge — healthy and
        transient-starting states keep the badge hidden.

        Auto-restart: bsky-saves' serve thread dies if it can't bind to
        port 47826 (e.g. another bsky-saves was already running at our
        launch). Without restart logic the helper stays dead forever even
        after the conflicting instance quits. On every tick where the
        supervisor thread is no longer alive, ask the supervisor to
        re-start; Supervisor.start() is a no-op if the thread is already
        running, so this is safe to call unconditionally.
        """
        import sys
        import time

        if self._badge_layer is None:
            return
        try:
            from bsky_saves_launcher.health import compute_health

            snapshot = compute_health(
                self._supervisor,
                last_ping_ok=self._last_ping_ok,
                helper_started=self._helper_started,
            )
            if snapshot.last_seen_ok is not None:
                self._last_ping_ok = snapshot.last_seen_ok

            if not self._supervisor.is_alive():
                # Helper thread is dead — restart. Reset the start clock so
                # the next few ticks see STARTING (within grace) rather
                # than UNRESPONSIVE.
                self._helper_started = time.monotonic()
                self._supervisor.start()

            show = _state_should_show_badge(snapshot.state)
            self._badge_layer.setHidden_(not show)
            if show:
                self._badge_layer.setBackgroundColor_(
                    _status_badge_color(snapshot.state).CGColor()
                )
        except Exception as exc:
            print(f"[tray] _on_health_tick failed: {exc!r}", file=sys.stderr)

    def icon_handle(self):
        """Return the underlying pystray.Icon (only valid after run() starts)."""
        return self._icon

    def refresh_icon(self) -> None:
        """Re-render the icon image based on supervisor state."""
        if self._icon is not None:
            self._icon.icon = _make_icon_image(running=self._supervisor.is_alive())
