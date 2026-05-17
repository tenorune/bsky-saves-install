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
        webbrowser.open(LOCAL_GUI_URL)

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
