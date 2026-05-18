"""Unit tests for launcher preferences (JSON-backed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsky_saves_launcher.preferences import Preferences, load_preferences, save_preferences


def test_load_returns_defaults_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: tmp_path / "does-not-exist.json",
    )
    prefs = load_preferences()
    assert prefs.show_in_dock is False
    assert prefs.start_at_login is False


def test_save_then_load_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pref_file = tmp_path / "preferences.json"
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: pref_file,
    )
    save_preferences(Preferences(show_in_dock=True, start_at_login=True))
    loaded = load_preferences()
    assert loaded.show_in_dock is True
    assert loaded.start_at_login is True


def test_save_creates_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "a" / "b" / "preferences.json"
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: nested,
    )
    save_preferences(Preferences(show_in_dock=True, start_at_login=False))
    assert nested.exists()


def test_load_recovers_from_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pref_file = tmp_path / "preferences.json"
    pref_file.write_text("{this is not valid json")
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: pref_file,
    )
    prefs = load_preferences()
    assert prefs.show_in_dock is False
    assert prefs.start_at_login is False


def test_load_recovers_from_unexpected_key_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pref_file = tmp_path / "preferences.json"
    pref_file.write_text('{"show_in_dock": "not a bool", "start_at_login": 1}')
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: pref_file,
    )
    prefs = load_preferences()
    assert prefs.show_in_dock is False
    assert prefs.start_at_login is False


def test_preferences_dataclass_is_immutable() -> None:
    prefs = Preferences(show_in_dock=True, start_at_login=False)
    with pytest.raises((AttributeError, Exception)):
        prefs.show_in_dock = False  # type: ignore[misc]
