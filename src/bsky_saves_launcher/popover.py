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

    def notify_helper_started(self) -> None:
        """Called by app.main() when supervisor.start() runs."""
        import time

        self._helper_started = time.monotonic()

    def show(self) -> None:
        """Show the popover anchored to the tray icon. Lazy-construct on first call."""
        if sys.platform != "darwin":
            return
        ak = _import_appkit()
        if self._popover is None:
            self._construct(ak)
        button = self._tray_icon_ref._status_item.button()
        self._popover.showRelativeToRect_ofView_preferredEdge_(
            button.bounds(),
            button,
            ak["NSRectEdgeMinY"],  # popover hangs below the menu-bar button
        )
        self._start_refresh_timer(ak)

    def _construct(self, ak) -> None:
        """Build the popover + a placeholder NSViewController on first show."""
        # Placeholder controller; Tasks 6 + 7 replace this with the real
        # navigation controller hosting Default + More views.
        controller = ak["NSViewController"].alloc().init()
        self._content_controller = controller
        popover = ak["NSPopover"].alloc().init()
        popover.setBehavior_(ak["NSPopoverBehaviorTransient"])
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
        """Refresh-timer callback. Replaced in Task 6 with a real view update."""
        from bsky_saves_launcher.health import compute_health

        snapshot = compute_health(
            self._supervisor,
            last_ping_ok=self._last_ping_ok,
            helper_started=self._helper_started,
        )
        if snapshot.last_seen_ok is not None:
            self._last_ping_ok = snapshot.last_seen_ok
        self._last_snapshot = snapshot

    def _stop_refresh_timer(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None
