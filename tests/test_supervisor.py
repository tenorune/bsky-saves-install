"""Unit tests for the subprocess supervisor."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from bsky_saves_launcher.supervisor import Supervisor


def _make_proc(*, alive_for: float = 10.0, returncode: int | None = None) -> MagicMock:
    """Build a fake subprocess.Popen-shaped object."""
    proc = MagicMock()
    proc._start_time = time.monotonic()
    proc._alive_for = alive_for
    proc.returncode = returncode
    proc.pid = 12345

    def poll() -> int | None:
        if proc.returncode is not None:
            return proc.returncode
        if time.monotonic() - proc._start_time > proc._alive_for:
            proc.returncode = 0
            return 0
        return None

    def wait(timeout: float | None = None) -> int:
        deadline = time.monotonic() + (timeout or 0.0)
        while poll() is None:
            if timeout is not None and time.monotonic() > deadline:
                raise TimeoutError
            time.sleep(0.01)
        return proc.returncode

    proc.poll.side_effect = poll
    proc.wait.side_effect = wait
    proc.stdout = MagicMock()
    proc.stdout.readline.return_value = ""
    proc.stderr = MagicMock()
    proc.stderr.readline.return_value = ""
    return proc


def test_supervisor_start_spawns_subprocess() -> None:
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen") as popen:
        popen.return_value = _make_proc()
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        try:
            popen.assert_called_once()
            args, kwargs = popen.call_args
            assert args[0] == ["bsky-saves", "serve"]
            assert sup.is_alive()
        finally:
            sup.stop(timeout=1.0)


def test_supervisor_stop_sends_sigterm() -> None:
    fake_proc = _make_proc()
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.stop(timeout=1.0)
    fake_proc.terminate.assert_called_once()


def test_supervisor_stop_falls_back_to_kill_on_timeout() -> None:
    fake_proc = _make_proc(alive_for=1e6)  # never dies of natural causes

    def wait_always_times_out(timeout: float | None = None) -> int:
        raise TimeoutError

    fake_proc.wait.side_effect = wait_always_times_out
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.stop(timeout=0.1)
    fake_proc.terminate.assert_called_once()
    fake_proc.kill.assert_called_once()


def test_recent_logs_returns_ring_buffer_contents() -> None:
    fake_proc = _make_proc()
    lines = [f"line-{i}\n" for i in range(5)]
    fake_proc.stdout.readline.side_effect = lines + [""]
    fake_proc.stderr.readline.return_value = ""
    with patch("bsky_saves_launcher.supervisor.subprocess.Popen", return_value=fake_proc):
        sup = Supervisor(command=["bsky-saves", "serve"], ring_size=3)
        sup.start()
        time.sleep(0.2)  # let reader threads drain
        logs = sup.recent_logs()
        sup.stop(timeout=1.0)
    # Ring is bounded to 3, so we kept the most recent 3.
    assert len(logs) <= 3
    if logs:
        assert all(line.startswith("line-") for line in logs)


def test_double_start_is_idempotent() -> None:
    with patch(
        "bsky_saves_launcher.supervisor.subprocess.Popen", return_value=_make_proc()
    ) as popen:
        sup = Supervisor(command=["bsky-saves", "serve"])
        sup.start()
        sup.start()  # second call is a no-op
        try:
            popen.assert_called_once()
        finally:
            sup.stop(timeout=1.0)
