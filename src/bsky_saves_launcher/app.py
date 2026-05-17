"""Launcher entry point — wires supervisor, tray, and status window together."""

from __future__ import annotations

import sys
from pathlib import Path

from bsky_saves_launcher.status_window import StatusWindow
from bsky_saves_launcher.supervisor import Supervisor
from bsky_saves_launcher.tray import TrayApp


# Invoke the bundled bsky-saves wheel by importing its CLI entry point with the
# bundled Python. We must NOT use sys.executable — inside a Briefcase .app it
# points at the .app's stub binary, which re-launches the whole app and causes
# a fork bomb. The real interpreter lives at <sys.prefix>/bin/python3.
HELPER_BOOTSTRAP = (
    "import sys; sys.argv[0] = 'bsky-saves'; "
    "from bsky_saves.cli import main; main()"
)


def _resolve_python() -> str:
    """Return a path to a real Python interpreter, never the .app stub."""
    candidate = Path(sys.prefix) / "bin" / "python3"
    if candidate.exists() and candidate.is_file():
        resolved = str(candidate)
    else:
        # Dev path (venv): sys.executable is the real Python.
        resolved = sys.executable

    # Safety net: refuse to spawn the .app stub. If we ever resolve to the same
    # binary that's running us AND that binary lives inside a .app bundle, we
    # would fork-bomb the launcher on every start().
    if resolved == sys.executable and ".app/Contents/MacOS/" in resolved:
        raise RuntimeError(
            f"Refusing to spawn helper via .app stub binary {resolved!r}; "
            "this would fork-bomb the launcher. The bundled Python at "
            f"{Path(sys.prefix) / 'bin' / 'python3'} was not found."
        )
    return resolved


def main() -> int:
    python = _resolve_python()
    helper_command = [python, "-c", HELPER_BOOTSTRAP, "serve"]

    supervisor = Supervisor(command=helper_command)
    status_window = StatusWindow(supervisor)

    supervisor.start()
    tray = TrayApp(supervisor, on_open_status=status_window.open)
    try:
        tray.run()
    finally:
        supervisor.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
