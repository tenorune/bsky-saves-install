"""On-demand status dialog for the launcher.

v0.1 is a placeholder. Clicking "Show status..." pops a native macOS dialog
with placeholder text. A richer in-process window is deferred to a follow-up
spec because Tkinter and pystray cannot share macOS's main runloop — the
Tk-based implementation from the original plan did not display. The follow-up
spec will use NSWindow via PyObjC (pystray's existing dependency on macOS).
"""

from __future__ import annotations

import subprocess
import sys
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bsky_saves_launcher.supervisor import Supervisor


_PLACEHOLDER_TEXT = (
    "Bsky Saves launcher\n\n"
    "Status-window contents are deferred to a follow-up spec. "
    "Helper is running locally on port 47826."
)


class StatusWindow:
    """Surface that displays a status dialog when opened."""

    def __init__(self, supervisor: Supervisor) -> None:  # noqa: F821
        self._supervisor = supervisor
        self._lock = threading.Lock()
        self._open_thread: threading.Thread | None = None

    def open(self) -> None:
        """Show the status dialog. No-op if one is already showing."""
        with self._lock:
            if self._open_thread is not None and self._open_thread.is_alive():
                return
            self._open_thread = threading.Thread(
                target=self._show, daemon=True, name="status-dialog"
            )
            self._open_thread.start()

    def _show(self) -> None:
        if sys.platform == "darwin":
            script = (
                f'display dialog "{_PLACEHOLDER_TEXT}" '
                'with title "Bsky Saves — status" '
                'buttons {"OK"} default button "OK" '
                'with icon note'
            )
            try:
                subprocess.run(
                    ["osascript", "-e", script],
                    check=False,
                    timeout=600.0,
                )
            except (subprocess.SubprocessError, OSError):
                pass
            return
        # Non-macOS dev fallback: just print to stderr so a developer running
        # the launcher outside a .app gets some feedback.
        print(_PLACEHOLDER_TEXT, file=sys.stderr)
