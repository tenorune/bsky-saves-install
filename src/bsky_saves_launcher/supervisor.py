"""Thread-based supervisor for the bsky-saves helper.

Runs a callable (typically `bsky_saves.cli.main(["serve"])`) in a daemon thread
inside the launcher process.

Why a thread, not a subprocess? Inside a Briefcase macOS .app, the only Python
entry point is the .app's stub binary at `Contents/MacOS/<name>` — there is no
standalone `python3` to spawn. Spawning the stub re-launches the whole app,
which fork-bombs the launcher. Running in-thread sidesteps that entirely.

Trade-off: Python threads cannot be cleanly killed. The Quit button must
terminate the whole launcher process (via os._exit() in app.py) — there is no
"stop the helper but keep the launcher alive" path in v0.1. That's acceptable
for the dogfood milestone; richer control belongs in the follow-up spec for
helper control endpoints.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any


class Supervisor:
    """Runs a callable in a daemon thread."""

    def __init__(
        self,
        target: Callable[..., Any],
        args: Sequence[Any] = (),
        *,
        on_exit: Callable[[int | None], None] | None = None,
    ) -> None:
        self._target = target
        self._args = tuple(args)
        self._on_exit = on_exit
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the helper thread. No-op if already running."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                daemon=True,
                name="bsky-saves-helper",
            )
            self._thread.start()

    def _run(self) -> None:
        try:
            self._target(*self._args)
        except SystemExit:
            # bsky-saves CLI calls sys.exit on argparse errors. Swallow so the
            # launcher's own SystemExit isn't preempted by the thread.
            pass
        except Exception:
            # The helper raised. v0.1 cannot surface this in the UI yet
            # (status-window contents are deferred). The exception still
            # appears in NSLog when launched as a .app.
            pass
        finally:
            if self._on_exit is not None:
                try:
                    self._on_exit(0)
                except Exception:
                    pass

    def stop(self, timeout: float = 5.0) -> None:
        """No-op. Python threads cannot be killed cleanly.

        The Quit handler in app.py calls os._exit() to terminate the whole
        process; that's what actually stops the helper. `stop()` exists so
        the interface stays uniform with future subprocess-based variants
        and so callers can use it without special-casing.
        """
        return

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def recent_logs(self) -> list[str]:
        """Log capture is deferred to the status-window-contents follow-up spec."""
        return []
