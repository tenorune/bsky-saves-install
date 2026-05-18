"""Unit tests for LaunchAgent install/uninstall."""

from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from bsky_saves_launcher.launchagent import (
    LAUNCH_AGENT_LABEL,
    LaunchAgentError,
    build_plist_data,
    install_launch_agent,
    is_launch_agent_installed,
    uninstall_launch_agent,
)


def test_label_is_reverse_dns() -> None:
    assert LAUNCH_AGENT_LABEL.startswith("net.lightseed.")


def test_build_plist_data_contains_required_keys() -> None:
    app_path = "/Applications/BSky Saves.app"
    data = build_plist_data(app_path=app_path)
    parsed = plistlib.loads(data)
    assert parsed["Label"] == LAUNCH_AGENT_LABEL
    assert parsed["RunAtLoad"] is True
    assert parsed["ProgramArguments"][0] == f"{app_path}/Contents/MacOS/BSky Saves"


def test_install_writes_to_launch_agents_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._launchctl_load",
        lambda path: None,
    )
    install_launch_agent(app_path="/Applications/BSky Saves.app")
    assert plist_path.exists()
    parsed = plistlib.loads(plist_path.read_bytes())
    assert parsed["Label"] == LAUNCH_AGENT_LABEL


def test_uninstall_removes_plist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    plist_path.write_bytes(build_plist_data(app_path="/Applications/BSky Saves.app"))
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._launchctl_unload",
        lambda path: None,
    )
    uninstall_launch_agent()
    assert not plist_path.exists()


def test_uninstall_when_not_installed_is_a_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plist_path = tmp_path / "missing.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._launchctl_unload",
        lambda path: None,
    )
    uninstall_launch_agent()  # should not raise


def test_is_installed_reflects_file_existence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    assert is_launch_agent_installed() is False
    plist_path.write_bytes(b"<plist version=\"1.0\"></plist>")
    assert is_launch_agent_installed() is True


def test_install_launchctl_failure_raises_launchagent_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )

    def _raise(_):
        raise RuntimeError("launchctl: load failed")

    monkeypatch.setattr("bsky_saves_launcher.launchagent._launchctl_load", _raise)
    with pytest.raises(LaunchAgentError):
        install_launch_agent(app_path="/Applications/BSky Saves.app")
