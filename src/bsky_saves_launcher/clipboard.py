"""Clipboard write helper for macOS.

Uses pbcopy (built into macOS) so we don't add a third-party clipboard
dependency. Caller is responsible for any user-facing feedback
('Copied' confirmation, error notification, etc.).
"""

from __future__ import annotations

import subprocess


class ClipboardError(RuntimeError):
    """Raised when the clipboard write fails."""


def copy_to_clipboard(text: str) -> None:
    """Write `text` to the macOS clipboard via pbcopy.

    Raises:
        ClipboardError: if pbcopy is missing or returns non-zero.
    """
    try:
        subprocess.run(
            ["pbcopy"],
            input=text,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ClipboardError(f"pbcopy failed: {exc!r}") from exc
    except FileNotFoundError as exc:
        raise ClipboardError("pbcopy not found (macOS-only)") from exc
