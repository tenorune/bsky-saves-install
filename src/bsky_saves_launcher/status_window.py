"""On-demand Tkinter status window for the launcher.

v0.1 is a placeholder. The window exists, can be opened from the tray, and is
re-focused on subsequent opens. Widget-level contents are spec'd in a follow-up
doc; do not add widgets here without referencing that spec.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bsky_saves_launcher.supervisor import Supervisor


class StatusWindow:
    """Lazily-constructed, singleton-per-launcher Tk window."""

    def __init__(self, supervisor: Supervisor) -> None:  # noqa: F821
        self._supervisor = supervisor
        self._root = None

    def open(self) -> None:
        """Open the window if not already open; focus it if it is."""
        if self._root is not None and self._is_alive():
            self._root.deiconify()
            self._root.lift()
            self._root.focus_force()
            return
        self._build()

    def _is_alive(self) -> bool:
        import tkinter as tk
        try:
            return bool(self._root and self._root.winfo_exists())
        except tk.TclError:
            return False

    def _build(self) -> None:
        import tkinter as tk
        root = tk.Tk()
        root.title("Bsky Saves — status")
        root.geometry("420x240")

        # Placeholder content. Replace per status-window-contents follow-up spec.
        label = tk.Label(
            root,
            text=(
                "Bsky Saves launcher\n\n"
                "Status-window contents are deferred to a follow-up spec.\n"
                "See docs/superpowers/specs/."
            ),
            justify="center",
            padx=16,
            pady=16,
        )
        label.pack(expand=True)

        def _on_close() -> None:
            root.withdraw()  # hide rather than destroy; reopen is cheaper

        root.protocol("WM_DELETE_WINDOW", _on_close)
        self._root = root
