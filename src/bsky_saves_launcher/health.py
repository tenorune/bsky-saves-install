"""Composite helper status — combines launcher and helper signals into one state.

State is a single user-facing enum; the five values map to five different
failure-mode wordings in the popover. See
docs/superpowers/specs/2026-05-17-status-window-contents.md D1.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from bsky_saves_launcher.supervisor import Supervisor


PING_URL = "http://127.0.0.1:47826/ping"
PING_TIMEOUT_S = 1.5


class HelperState(enum.Enum):
    """Composite state combining launcher Supervisor and helper /ping signals."""

    RUNNING = "running"
    STARTING = "starting"
    STOPPED = "stopped"
    UNRESPONSIVE = "unresponsive"
    PORT_CONFLICT = "port_conflict"


@dataclass(frozen=True)
class HealthSnapshot:
    """A single read of helper health. Immutable so the popover can hand it off
    to any view without worrying about mutation."""

    state: HelperState
    uptime_seconds: float | None
    last_seen_ok: float | None
    helper_version: str | None
    gui_version: str | None


def compute_health(
    supervisor: Supervisor,
    *,
    last_ping_ok: float | None,
    helper_started: float | None,
) -> HealthSnapshot:
    """Build a HealthSnapshot from the current launcher and helper state.

    Args:
        supervisor: the launcher's Supervisor instance.
        last_ping_ok: monotonic-clock seconds of the most recent successful
            /ping the popover has seen so far (or None if no success yet
            this session).
        helper_started: monotonic-clock seconds when supervisor.start() was
            called (or None if helper hasn't started this session).

    Returns:
        A HealthSnapshot with the composite state and metadata.
    """
    alive = supervisor.is_alive()
    ping_ok = False
    helper_version: str | None = None
    gui_version: str | None = None
    try:
        resp = httpx.get(PING_URL, timeout=PING_TIMEOUT_S)
        if resp.status_code == 200:
            ping_ok = True
            try:
                payload = resp.json()
            except Exception:
                payload = {}
            v = payload.get("version")
            g = payload.get("gui_bundled")
            helper_version = v if isinstance(v, str) else None
            gui_version = g if isinstance(g, str) else None
    except Exception:
        ping_ok = False

    now = time.monotonic()
    if ping_ok:
        last_ping_ok = now

    if alive and ping_ok:
        state = HelperState.RUNNING
    elif alive and not ping_ok and last_ping_ok is None:
        state = HelperState.STARTING
    elif alive and not ping_ok and last_ping_ok is not None:
        state = HelperState.UNRESPONSIVE
    elif not alive and ping_ok:
        state = HelperState.PORT_CONFLICT
    else:
        state = HelperState.STOPPED

    if alive and helper_started is not None:
        uptime: float | None = now - helper_started
    else:
        uptime = None

    return HealthSnapshot(
        state=state,
        uptime_seconds=uptime,
        last_seen_ok=last_ping_ok,
        helper_version=helper_version,
        gui_version=gui_version,
    )
