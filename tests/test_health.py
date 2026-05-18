"""Unit tests for composite helper status."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from bsky_saves_launcher.health import HelperState, compute_health


def _fake_supervisor(*, alive: bool) -> MagicMock:
    sup = MagicMock()
    sup.is_alive.return_value = alive
    return sup


def _fake_ping_response(status_code: int, body: dict[str, Any] | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {
        "name": "bsky-saves",
        "version": "0.6.6",
        "protocol": "2",
        "gui_bundled": "0.6.3",
    }
    return resp


def test_running_state_when_supervisor_alive_and_ping_200() -> None:
    sup = _fake_supervisor(alive=True)
    with patch("bsky_saves_launcher.health.httpx.get", return_value=_fake_ping_response(200)):
        now = time.monotonic()
        snap = compute_health(sup, last_ping_ok=now, helper_started=now - 47)
    assert snap.state is HelperState.RUNNING
    assert snap.uptime_seconds == pytest.approx(47, abs=1)
    assert snap.helper_version == "0.6.6"
    assert snap.gui_version == "0.6.3"


def test_starting_state_when_supervisor_alive_but_ping_never_succeeded() -> None:
    sup = _fake_supervisor(alive=True)
    with patch(
        "bsky_saves_launcher.health.httpx.get",
        side_effect=Exception("connection refused"),
    ):
        snap = compute_health(sup, last_ping_ok=None, helper_started=time.monotonic())
    assert snap.state is HelperState.STARTING


def test_unresponsive_when_supervisor_alive_but_ping_fails_now() -> None:
    sup = _fake_supervisor(alive=True)
    last_ok = time.monotonic() - 30  # had a good ping 30s ago
    with patch(
        "bsky_saves_launcher.health.httpx.get",
        side_effect=Exception("timeout"),
    ):
        snap = compute_health(sup, last_ping_ok=last_ok, helper_started=last_ok - 10)
    assert snap.state is HelperState.UNRESPONSIVE


def test_stopped_when_supervisor_dead_and_no_ping() -> None:
    sup = _fake_supervisor(alive=False)
    with patch(
        "bsky_saves_launcher.health.httpx.get",
        side_effect=Exception("connection refused"),
    ):
        snap = compute_health(sup, last_ping_ok=None, helper_started=None)
    assert snap.state is HelperState.STOPPED


def test_port_conflict_when_supervisor_dead_but_something_answers_ping() -> None:
    sup = _fake_supervisor(alive=False)
    with patch("bsky_saves_launcher.health.httpx.get", return_value=_fake_ping_response(200)):
        snap = compute_health(sup, last_ping_ok=time.monotonic(), helper_started=None)
    assert snap.state is HelperState.PORT_CONFLICT


def test_snapshot_records_last_seen_ok_when_ping_succeeds() -> None:
    sup = _fake_supervisor(alive=True)
    now = time.monotonic()
    with patch("bsky_saves_launcher.health.httpx.get", return_value=_fake_ping_response(200)):
        snap = compute_health(sup, last_ping_ok=None, helper_started=now)
    assert snap.last_seen_ok is not None
    assert abs(snap.last_seen_ok - time.monotonic()) < 1.0


def test_snapshot_is_immutable() -> None:
    sup = _fake_supervisor(alive=True)
    with patch("bsky_saves_launcher.health.httpx.get", return_value=_fake_ping_response(200)):
        snap = compute_health(sup, last_ping_ok=None, helper_started=time.monotonic())
    with pytest.raises((AttributeError, Exception)):
        snap.state = HelperState.STOPPED  # type: ignore[misc]


def test_helper_version_and_gui_version_none_when_ping_fails() -> None:
    sup = _fake_supervisor(alive=True)
    with patch(
        "bsky_saves_launcher.health.httpx.get",
        side_effect=Exception("connection refused"),
    ):
        snap = compute_health(sup, last_ping_ok=None, helper_started=time.monotonic())
    assert snap.helper_version is None
    assert snap.gui_version is None
