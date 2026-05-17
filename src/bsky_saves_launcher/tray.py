"""Menu-bar / system-tray icon for the launcher.

Renders a pystray icon, wires up a minimal v0.1 menu (Open GUI, Quit), and
exposes a callback hook for opening the status window on icon click.
"""

from __future__ import annotations

import os
import webbrowser
from collections.abc import Callable
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw

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


def _make_icon_image(*, running: bool) -> Image.Image:
    """Render a 64x64 RGBA icon. Green dot when running, gray when stopped."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (60, 200, 90, 255) if running else (160, 160, 160, 255)
    draw.ellipse((8, 8, 56, 56), fill=color)
    return img


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
            pystray.MenuItem(
                "Show status...",
                self._on_default,
                default=True,
                visible=False,  # invoked by icon click, not shown in menu
            ),
            pystray.MenuItem("Open GUI", self._on_open_gui),
            pystray.MenuItem("Quit", self._on_quit),
        )
        self._icon = pystray.Icon(
            name="bsky-saves",
            icon=_make_icon_image(running=self._supervisor.is_alive()),
            title="Bsky Saves",
            menu=menu,
        )
        self._icon.run()

    def refresh_icon(self) -> None:
        """Re-render the icon image based on supervisor state."""
        if self._icon is not None:
            self._icon.icon = _make_icon_image(running=self._supervisor.is_alive())
