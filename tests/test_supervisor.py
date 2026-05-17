"""Unit tests for the thread-based supervisor."""

from __future__ import annotations

import threading
import time

from bsky_saves_launcher.supervisor import Supervisor


def test_supervisor_start_runs_target_in_thread() -> None:
    started = threading.Event()
    release = threading.Event()

    def target() -> None:
        started.set()
        release.wait(timeout=2.0)

    sup = Supervisor(target=target)
    sup.start()
    assert started.wait(timeout=1.0), "target did not run"
    assert sup.is_alive()
    release.set()
    for _ in range(20):
        if not sup.is_alive():
            break
        time.sleep(0.05)
    assert not sup.is_alive()


def test_supervisor_double_start_is_idempotent() -> None:
    call_count = 0
    release = threading.Event()

    def target() -> None:
        nonlocal call_count
        call_count += 1
        release.wait(timeout=2.0)

    sup = Supervisor(target=target)
    sup.start()
    sup.start()  # second call: no-op while first is still running
    time.sleep(0.1)
    assert call_count == 1
    release.set()


def test_supervisor_target_receives_args() -> None:
    seen: list[tuple] = []

    def target(argv: list[str]) -> None:
        seen.append(tuple(argv))

    sup = Supervisor(target=target, args=(["serve", "--port", "47826"],))
    sup.start()
    for _ in range(20):
        if seen:
            break
        time.sleep(0.05)
    assert seen == [("serve", "--port", "47826")]


def test_supervisor_swallows_system_exit_from_target() -> None:
    def target() -> None:
        raise SystemExit(2)

    on_exit_seen: list[int | None] = []
    sup = Supervisor(target=target, on_exit=lambda rc: on_exit_seen.append(rc))
    sup.start()
    for _ in range(20):
        if on_exit_seen:
            break
        time.sleep(0.05)
    assert on_exit_seen == [0]


def test_supervisor_stop_is_safe_to_call() -> None:
    sup = Supervisor(target=lambda: None)
    sup.stop()  # no-op even before start
    sup.start()
    time.sleep(0.05)
    sup.stop()  # no-op after thread has finished


def test_recent_logs_returns_empty_in_v01() -> None:
    sup = Supervisor(target=lambda: None)
    sup.start()
    time.sleep(0.05)
    assert sup.recent_logs() == []
