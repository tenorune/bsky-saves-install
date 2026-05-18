"""Pairing-token reader.

The pairing token is a 32-hex-char secret the helper writes to
~/Library/Application Support/bsky-saves/token (mode 0o600). The hosted
PWA at saves.lightseed.net prompts the user to paste it during pairing.

This module reads the token so the launcher can offer a 'Copy pairing
token' affordance without rendering the value in the UI. The value is
returned to the caller and copied to the clipboard from there; the
token never appears in the popover, menu, or any log.

See:
- docs/superpowers/specs/2026-05-17-status-window-contents.md D2
- bsky-saves' own session-token spec for the file's lifecycle
"""

from __future__ import annotations

from pathlib import Path


def _token_path() -> Path:
    """Platform-conventional location of the pairing-token file.

    macOS: ~/Library/Application Support/bsky-saves/token
    Tests monkeypatch this to point at a temporary file.
    """
    return Path.home() / "Library" / "Application Support" / "bsky-saves" / "token"


def read_pairing_token() -> str | None:
    """Read the pairing token from disk, or return None.

    Returns:
        The token as a string (whitespace-stripped) if the file exists
        and is non-empty; None otherwise. Callers should treat None as
        'no token yet — helper hasn't started or file isn't where we
        expect' and surface a helpful message to the user.
    """
    path = _token_path()
    try:
        contents = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError:
        return None
    stripped = contents.strip()
    return stripped or None
