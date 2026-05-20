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


def test_build_plist_data_uses_open_a_app_for_correct_icon() -> None:
    """ProgramArguments must use `/usr/bin/open -a <app_path>` so Login Items
    resolves the .app's icon (rather than rendering a terminal placeholder)."""
    app_path = "/Applications/BSky Saves.app"
    data = build_plist_data(app_path=app_path)
    parsed = plistlib.loads(data)
    assert parsed["Label"] == LAUNCH_AGENT_LABEL
    assert parsed["RunAtLoad"] is True
    assert parsed["ProgramArguments"] == ["/usr/bin/open", "-a", app_path]


def test_install_writes_to_launch_agents_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """install_launch_agent writes the plist (and does NOT call launchctl —
    that would launch a duplicate instance right now)."""
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    install_launch_agent(app_path="/Applications/BSky Saves.app")
    assert plist_path.exists()
    parsed = plistlib.loads(plist_path.read_bytes())
    assert parsed["Label"] == LAUNCH_AGENT_LABEL


def test_uninstall_removes_plist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """uninstall removes the plist (and does NOT call launchctl unload —
    that would kill the currently-running launcher)."""
    plist_path = tmp_path / "net.lightseed.bsky-saves-launcher.plist"
    plist_path.write_bytes(build_plist_data(app_path="/Applications/BSky Saves.app"))
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
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


def test_install_raises_launchagent_error_on_filesystem_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If writing the plist fails (e.g. permissions denied), surface
    LaunchAgentError so the caller can revert UI state."""
    # Point at a path whose parent doesn't exist AND can't be created
    # (use a path under a regular file).
    sentinel = tmp_path / "not-a-directory"
    sentinel.write_text("regular file, not a dir")
    plist_path = sentinel / "net.lightseed.bsky-saves-launcher.plist"
    monkeypatch.setattr(
        "bsky_saves_launcher.launchagent._plist_path",
        lambda: plist_path,
    )
    with pytest.raises(LaunchAgentError):
        install_launch_agent(app_path="/Applications/BSky Saves.app")
