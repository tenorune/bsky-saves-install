"""Unit tests for the clipboard write helper."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from bsky_saves_launcher.clipboard import ClipboardError, copy_to_clipboard


def test_writes_to_pbcopy_via_stdin() -> None:
    with patch("bsky_saves_launcher.clipboard.subprocess.run") as run:
        run.return_value = MagicMock(returncode=0)
        copy_to_clipboard("hello")
        run.assert_called_once()
        args, kwargs = run.call_args
        assert args[0] == ["pbcopy"]
        assert kwargs.get("input") == "hello"
        assert kwargs.get("text") is True
        assert kwargs.get("check") is True


def test_raises_clipboard_error_on_pbcopy_failure() -> None:
    with patch("bsky_saves_launcher.clipboard.subprocess.run") as run:
        run.side_effect = subprocess.CalledProcessError(returncode=1, cmd=["pbcopy"])
        with pytest.raises(ClipboardError):
            copy_to_clipboard("hello")


def test_raises_clipboard_error_when_pbcopy_missing() -> None:
    with patch("bsky_saves_launcher.clipboard.subprocess.run") as run:
        run.side_effect = FileNotFoundError("pbcopy")
        with pytest.raises(ClipboardError):
            copy_to_clipboard("hello")
