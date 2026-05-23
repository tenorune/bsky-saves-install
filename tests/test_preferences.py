"""Unit tests for launcher preferences (JSON-backed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsky_saves_launcher.preferences import Preferences, load_preferences, save_preferences


def _patch_paths(
    monkeypatch: pytest.MonkeyPatch,
    *,
    new: Path,
    legacy: Path | None = None,
) -> None:
    """Monkeypatch both the canonical and legacy preferences paths.

    Always patches both so tests can't leak through to a real file on
    the host. Pass `legacy=None` (default) for a non-existent legacy
    path — i.e. fresh-install scenarios.
    """
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._preferences_path",
        lambda: new,
    )
    monkeypatch.setattr(
        "bsky_saves_launcher.preferences._legacy_preferences_path",
        lambda: legacy if legacy is not None else (new.parent / "nonexistent-legacy.json"),
    )


def test_load_returns_defaults_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paths(monkeypatch, new=tmp_path / "does-not-exist.json")
    prefs = load_preferences()
    assert prefs.start_at_login is False


def test_save_then_load_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_paths(monkeypatch, new=tmp_path / "launcher-preferences.json")
    save_preferences(Preferences(start_at_login=True))
    loaded = load_preferences()
    assert loaded.start_at_login is True


def test_save_creates_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nested = tmp_path / "a" / "b" / "launcher-preferences.json"
    _patch_paths(monkeypatch, new=nested)
    save_preferences(Preferences(start_at_login=False))
    assert nested.exists()


def test_load_recovers_from_malformed_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pref_file = tmp_path / "launcher-preferences.json"
    pref_file.write_text("{this is not valid json")
    _patch_paths(monkeypatch, new=pref_file)
    prefs = load_preferences()
    assert prefs.start_at_login is False


def test_load_recovers_from_unexpected_key_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pref_file = tmp_path / "launcher-preferences.json"
    pref_file.write_text('{"start_at_login": 1}')
    _patch_paths(monkeypatch, new=pref_file)
    prefs = load_preferences()
    assert prefs.start_at_login is False


def test_legacy_show_in_dock_key_is_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A preferences file written by a pre-v0.3.x version of the launcher
    may carry a 'show_in_dock' key; loading must not raise."""
    pref_file = tmp_path / "launcher-preferences.json"
    pref_file.write_text('{"show_in_dock": true, "start_at_login": true}')
    _patch_paths(monkeypatch, new=pref_file)
    prefs = load_preferences()
    assert prefs.start_at_login is True
    assert not hasattr(prefs, "show_in_dock")


def test_load_falls_back_to_legacy_path_when_new_path_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v0.3.x users have their preferences at
    Application Support/bsky-saves-launcher/preferences.json. When the
    canonical (new) path doesn't exist yet but the legacy path does,
    load_preferences should read from the legacy path so the user's
    start_at_login choice survives the upgrade."""
    new_path = tmp_path / "new" / "launcher-preferences.json"
    legacy_path = tmp_path / "legacy" / "preferences.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text('{"start_at_login": true}')
    _patch_paths(monkeypatch, new=new_path, legacy=legacy_path)
    prefs = load_preferences()
    assert prefs.start_at_login is True
    # New path still doesn't exist — load doesn't write through.
    assert not new_path.exists()


def test_save_migrates_to_new_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First save after upgrade writes to the new path (regardless of
    whether legacy file exists). Subsequent loads read the new path
    without consulting legacy."""
    new_path = tmp_path / "new" / "launcher-preferences.json"
    legacy_path = tmp_path / "legacy" / "preferences.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text('{"start_at_login": true}')
    _patch_paths(monkeypatch, new=new_path, legacy=legacy_path)

    # Save uses the new path.
    save_preferences(Preferences(start_at_login=True))
    assert new_path.exists()

    # Subsequent load reads new path.
    loaded = load_preferences()
    assert loaded.start_at_login is True
    # Legacy file still in place — we don't delete it.
    assert legacy_path.exists()


def test_new_path_takes_precedence_over_legacy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If both files exist (e.g. mid-migration state), the canonical
    new path wins."""
    new_path = tmp_path / "new" / "launcher-preferences.json"
    legacy_path = tmp_path / "legacy" / "preferences.json"
    new_path.parent.mkdir(parents=True)
    legacy_path.parent.mkdir(parents=True)
    new_path.write_text('{"start_at_login": false}')
    legacy_path.write_text('{"start_at_login": true}')
    _patch_paths(monkeypatch, new=new_path, legacy=legacy_path)
    prefs = load_preferences()
    assert prefs.start_at_login is False


def test_preferences_dataclass_is_immutable() -> None:
    prefs = Preferences(start_at_login=False)
    with pytest.raises((AttributeError, Exception)):
        prefs.start_at_login = True  # type: ignore[misc]
