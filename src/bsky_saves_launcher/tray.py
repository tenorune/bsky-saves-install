"""Menu-bar / system-tray icon for the launcher.

Renders a pystray icon, wires up a minimal v0.1 menu (Open GUI, Quit), and
exposes a callback hook for opening the status window on icon click.
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from typing import TYPE_CHECKING

from PIL import Image

if TYPE_CHECKING:
    import pystray

from bsky_saves_launcher.supervisor import Supervisor

LOCAL_GUI_URL = "http://127.0.0.1:47826/"

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


class TrayApp:
    """Owns the pystray icon and dispatches its menu items."""

    def __init__(
        self,
        supervisor: Supervisor,
        *,
        on_open_status: Callable[[], None],
    ) -> None:
        self._supervisor = supervisor
        self._on_open_status = on_open_status
        self._icon: pystray.Icon | None = None

    def _on_open_gui(self, icon, item) -> None:  # noqa: F821
        _open_or_focus_gui()

    # NOTE: "Copy pairing token" was a tray menu item in v0.2.0 but caused two
    # UX issues: (1) macOS `display notification` adds a "Show" button that
    # opens Script Editor, which is jarring; (2) the action belongs in the
    # status surface (popover), not the menu. The functionality lives in
    # bsky_saves_launcher.token + .clipboard; reattach via the popover's
    # Copy-token button when that lands. See
    # docs/superpowers/specs/2026-05-17-status-window-contents.md D2.

    def _on_quit(self, icon, item) -> None:  # noqa: F821
        # The helper runs in a daemon thread inside this process and can't be
        # stopped cleanly (Python threads aren't killable). Terminate the
        # whole process to take it down.
        icon.stop()
        os._exit(0)

    def _on_default(self, icon, item) -> None:  # noqa: F821
        # Triggered by left-click on the icon (pystray default action).
        self._on_open_status()

    def run(self) -> None:
        """Block on the pystray event loop. Must be called on the main thread."""
        import pystray

        menu = pystray.Menu(
            pystray.MenuItem("Show status...", self._on_default),
            pystray.MenuItem("Open GUI", self._on_open_gui),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            name="bsky-saves",
            icon=_make_icon_image(running=self._supervisor.is_alive()),
            title="BSky Saves",
            menu=menu,
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

    def icon_handle(self):
        """Return the underlying pystray.Icon (only valid after run() starts)."""
        return self._icon

    def refresh_icon(self) -> None:
        """Re-render the icon image based on supervisor state."""
        if self._icon is not None:
            self._icon.icon = _make_icon_image(running=self._supervisor.is_alive())
