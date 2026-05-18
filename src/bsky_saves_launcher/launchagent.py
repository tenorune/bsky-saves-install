"""LaunchAgent install/uninstall for Start-at-login.

Writes a plist to ~/Library/LaunchAgents/<label>.plist. macOS launchd
reads this directory at user login and auto-loads every plist it finds;
removal just deletes the file. We intentionally do NOT call
`launchctl load`/`unload` because that would (a) immediately start a
second copy of the app on enable and (b) kill the currently-running
copy on disable. The semantic users want from "Start at login" is
"start at next login", not "start now".

ProgramArguments uses `/usr/bin/open -a <app_bundle_path>` so macOS
treats the launch as an app-bundle activation. This makes Login Items
in System Settings (and Background Activity) resolve the correct
icon from the bundle's Info.plist + .icns. Pointing directly at
Contents/MacOS/<name> instead produces a generic terminal icon.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

LAUNCH_AGENT_LABEL = "net.lightseed.bsky-saves-launcher"


class LaunchAgentError(RuntimeError):
    """Raised when launchagent operations can't complete."""


def _plist_path() -> Path:
    """Platform-conventional LaunchAgent location."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def build_plist_data(*, app_path: str) -> bytes:
    """Build the LaunchAgent plist contents.

    Args:
        app_path: absolute path to the BSky Saves .app bundle in /Applications
            (or wherever the user installed it).

    Returns:
        Serialized plist bytes. Uses `/usr/bin/open -a <app_path>` as the
        program so macOS treats this as an app-bundle activation; that's
        what makes Login Items display the correct icon (rather than a
        generic terminal one).
    """
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": ["/usr/bin/open", "-a", app_path],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }
    return plistlib.dumps(payload)


def install_launch_agent(*, app_path: str) -> None:
    """Write the plist. Takes effect at next user login.

    Intentionally does NOT call `launchctl load` — that would launch a
    second instance of the app immediately, which isn't what "Start at
    login" means to a user.

    Raises:
        LaunchAgentError: if the plist write fails.
    """
    plist_path = _plist_path()
    data = build_plist_data(app_path=app_path)
    try:
        plist_path.parent.mkdir(parents=True, exist_ok=True)
        plist_path.write_bytes(data)
    except OSError as exc:
        raise LaunchAgentError(f"failed to write {plist_path}: {exc!r}") from exc


def uninstall_launch_agent() -> None:
    """Remove the plist. Takes effect at next user login.

    Intentionally does NOT call `launchctl unload` — that would kill the
    currently-running launcher process, which would be surprising to a
    user who just toggled off a future-tense preference.

    No-op if not installed.

    Raises:
        LaunchAgentError: if the plist removal fails.
    """
    plist_path = _plist_path()
    if not plist_path.exists():
        return
    try:
        plist_path.unlink()
    except OSError as exc:
        raise LaunchAgentError(f"failed to remove {plist_path}: {exc!r}") from exc


def is_launch_agent_installed() -> bool:
    """Return True if the plist exists on disk (proxy for 'enabled')."""
    return _plist_path().exists()
