"""Launcher preferences — JSON-backed, co-located with the helper's
config dir.

One boolean preference in v0.3.x+: start_at_login. Defaults to False
(no autostart). Defensive parsing so a corrupted preferences file
degrades to defaults rather than crashing the launcher on startup.

Path: ~/Library/Application Support/bsky-saves/launcher-preferences.json
— under the same parent directory as the helper's `token` file (and
the v0.4.0 `status.json` mirror). Keeps all bsky-saves state in one
place rather than scattering a separate `bsky-saves-launcher/` dir.

Migration: the v0.3.x location
~/Library/Application Support/bsky-saves-launcher/preferences.json
is still read on load if the new-path file is absent, then copied to
the new path on next save. Old file is left in place; users can
remove the empty `bsky-saves-launcher/` directory manually if they
want. We don't `os.unlink` it ourselves to avoid surprising users
who may have other tooling pointing at the legacy path.

A previous version included show_in_dock, but macOS's recent-apps
Dock cache made the toggle unreliable (clicking the leftover Dock
entry reverted the policy under the user's feet). The launcher is
now hardcoded menu-bar-only via LSUIElement=true in Info.plist +
runtime NSApp.setActivationPolicy_(Accessory).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Preferences:
    """Immutable preferences snapshot."""

    start_at_login: bool = False


def _preferences_path() -> Path:
    """Platform-conventional location of the preferences file.

    macOS: ~/Library/Application Support/bsky-saves/launcher-preferences.json
    — co-located with the helper's token and status files. Tests
    monkeypatch this to a tmp_path.
    """
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "bsky-saves"
        / "launcher-preferences.json"
    )


def _legacy_preferences_path() -> Path:
    """v0.3.x location, read as fallback on load.

    macOS: ~/Library/Application Support/bsky-saves-launcher/preferences.json
    """
    return (
        Path.home()
        / "Library"
        / "Application Support"
        / "bsky-saves-launcher"
        / "preferences.json"
    )


def _parse_contents(contents: str) -> Preferences:
    try:
        data = json.loads(contents)
    except (ValueError, TypeError):
        return Preferences()
    if not isinstance(data, dict):
        return Preferences()
    start_at_login = data.get("start_at_login")
    return Preferences(
        start_at_login=start_at_login if isinstance(start_at_login, bool) else False,
    )


def load_preferences() -> Preferences:
    """Read preferences from disk; return defaults on any failure.

    Tries the canonical path first. If that's absent, falls back to
    the v0.3.x legacy path so existing users don't lose their
    start_at_login choice on upgrade — the next save_preferences()
    call writes the new path and effectively migrates.
    """
    path = _preferences_path()
    try:
        return _parse_contents(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError):
        pass

    # Fallback to legacy path. Best-effort: any I/O failure → defaults.
    legacy = _legacy_preferences_path()
    try:
        return _parse_contents(legacy.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError):
        return Preferences()


def save_preferences(prefs: Preferences) -> None:
    """Atomically write preferences to disk."""
    path = _preferences_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps({"start_at_login": prefs.start_at_login}, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
