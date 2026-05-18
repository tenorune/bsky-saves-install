"""LaunchAgent install/uninstall for Start-at-login.

Writes a plist to ~/Library/LaunchAgents/<label>.plist and asks launchd
to load it. Uninstall does the reverse. Both operations are
best-effort: filesystem errors raise LaunchAgentError; launchctl
failures (already-loaded, etc.) are surfaced but the plist write side
is what actually controls the boot behavior.
"""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

LAUNCH_AGENT_LABEL = "net.lightseed.bsky-saves-launcher"


class LaunchAgentError(RuntimeError):
    """Raised when launchagent operations can't complete."""


def _plist_path() -> Path:
    """Platform-conventional LaunchAgent location."""
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def _launchctl_load(plist_path: Path) -> None:
    """Ask launchd to load this LaunchAgent now."""
    subprocess.run(
        ["launchctl", "load", "-w", str(plist_path)],
        check=True,
        capture_output=True,
    )


def _launchctl_unload(plist_path: Path) -> None:
    """Ask launchd to unload this LaunchAgent now."""
    subprocess.run(
        ["launchctl", "unload", "-w", str(plist_path)],
        check=True,
        capture_output=True,
    )


def build_plist_data(*, app_path: str) -> bytes:
    """Build the LaunchAgent plist contents."""
    binary_path = f"{app_path}/Contents/MacOS/BSky Saves"
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [binary_path],
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
    }
    return plistlib.dumps(payload)


def install_launch_agent(*, app_path: str) -> None:
    """Write the plist and ask launchd to load it.

    Raises:
        LaunchAgentError: if the plist write or launchctl load fails.
    """
    plist_path = _plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    data = build_plist_data(app_path=app_path)
    try:
        plist_path.write_bytes(data)
    except OSError as exc:
        raise LaunchAgentError(f"failed to write {plist_path}: {exc!r}") from exc
    try:
        _launchctl_load(plist_path)
    except Exception as exc:
        raise LaunchAgentError(f"launchctl load failed: {exc!r}") from exc


def uninstall_launch_agent() -> None:
    """Remove the plist and ask launchd to forget about it.

    No-op if not installed. Best-effort: launchctl unload failures are
    ignored (already unloaded, not loaded, etc.); plist removal is the
    authoritative action.
    """
    plist_path = _plist_path()
    if not plist_path.exists():
        return
    try:
        _launchctl_unload(plist_path)
    except Exception:
        pass
    try:
        plist_path.unlink()
    except OSError as exc:
        raise LaunchAgentError(f"failed to remove {plist_path}: {exc!r}") from exc


def is_launch_agent_installed() -> bool:
    """Return True if the plist exists on disk (proxy for 'enabled')."""
    return _plist_path().exists()
