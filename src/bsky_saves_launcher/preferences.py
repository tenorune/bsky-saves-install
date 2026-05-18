"""Launcher preferences — JSON-backed at platform-conventional path.

Two boolean preferences in v1: show_in_dock, start_at_login. Both default
to False (menu-bar-only daemon; no autostart). Defensive parsing so a
corrupted preferences file degrades to defaults rather than crashing the
launcher on startup.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Preferences:
    """Immutable preferences snapshot."""

    show_in_dock: bool = False
    start_at_login: bool = False


def _preferences_path() -> Path:
    """Platform-conventional location of the preferences file.

    macOS: ~/Library/Application Support/bsky-saves-launcher/preferences.json
    Tests monkeypatch this to a tmp_path.
    """
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "bsky-saves-launcher"
        / "preferences.json"
    )


def load_preferences() -> Preferences:
    """Read preferences from disk; return defaults on any failure."""
    path = _preferences_path()
    try:
        contents = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return Preferences()

    try:
        data = json.loads(contents)
    except (ValueError, TypeError):
        return Preferences()

    if not isinstance(data, dict):
        return Preferences()

    show_in_dock = data.get("show_in_dock")
    start_at_login = data.get("start_at_login")
    return Preferences(
        show_in_dock=show_in_dock if isinstance(show_in_dock, bool) else False,
        start_at_login=start_at_login if isinstance(start_at_login, bool) else False,
    )


def save_preferences(prefs: Preferences) -> None:
    """Atomically write preferences to disk."""
    path = _preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(
            {"show_in_dock": prefs.show_in_dock, "start_at_login": prefs.start_at_login},
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(path)
