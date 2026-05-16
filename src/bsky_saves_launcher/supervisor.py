"""Subprocess supervisor for `bsky-saves serve`.

Owns the child process across the launcher's lifetime. Captures stdout/stderr
into a bounded ring buffer. Exposes a simple interface: start, stop, is_alive,
recent_logs, and an on_exit callback.
"""

from __future__ import annotations

import subprocess
import threading
from collections import deque
from collections.abc import Callable, Sequence


class Supervisor:
    """Spawns and supervises a long-running child process."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        ring_size: int = 200,
        on_exit: Callable[[int | None], None] | None = None,
    ) -> None:
        self._command = list(command)
        self._ring: deque[str] = deque(maxlen=ring_size)
        self._ring_lock = threading.Lock()
        self._on_exit = on_exit
        self._proc: subprocess.Popen[str] | None = None
        self._readers: list[threading.Thread] = []
        self._exit_watcher: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the subprocess. No-op if already running."""
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            self._proc = subprocess.Popen(
                self._command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            self._readers = [
                threading.Thread(
                    target=self._drain,
                    args=(self._proc.stdout,),
                    daemon=True,
                    name="bsi-stdout",
                ),
                threading.Thread(
                    target=self._drain,
                    args=(self._proc.stderr,),
                    daemon=True,
                    name="bsi-stderr",
                ),
            ]
            for t in self._readers:
                t.start()
            self._exit_watcher = threading.Thread(
                target=self._watch_exit,
                daemon=True,
                name="bsi-exit-watch",
            )
            self._exit_watcher.start()

    def _drain(self, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                with self._ring_lock:
                    self._ring.append(line.rstrip("\n"))
        except (ValueError, OSError):
            # Stream closed during shutdown.
            pass

    def _watch_exit(self) -> None:
        if self._proc is None:
            return
        try:
            rc = self._proc.wait()
        except (subprocess.TimeoutExpired, TimeoutError, OSError):
            # Process was killed or stream closed during shutdown.
            return
        if self._on_exit is not None:
            try:
                self._on_exit(rc)
            except Exception:
                # Callback errors must not crash the watcher thread.
                pass

    def stop(self, timeout: float = 5.0) -> None:
        """Terminate the subprocess. SIGTERM first, SIGKILL on timeout."""
        with self._lock:
            proc = self._proc
            if proc is None:
                return
            if proc.poll() is not None:
                self._proc = None
                return
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, TimeoutError):
                proc.kill()
                try:
                    proc.wait(timeout=timeout)
                except (subprocess.TimeoutExpired, TimeoutError):
                    pass
            self._proc = None

    def is_alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None

    def recent_logs(self) -> list[str]:
        with self._ring_lock:
            return list(self._ring)
