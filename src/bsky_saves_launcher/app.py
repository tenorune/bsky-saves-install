"""Launcher entry point — wires supervisor, tray, and status window together."""

from __future__ import annotations

import sys

from bsky_saves.cli import main as bsky_saves_main

from bsky_saves_launcher.status_window import StatusWindow
from bsky_saves_launcher.supervisor import Supervisor
from bsky_saves_launcher.tray import TrayApp

HELPER_ARGV = ["serve"]


def main() -> int:
    supervisor = Supervisor(target=bsky_saves_main, args=(HELPER_ARGV,))
    status_window = StatusWindow(supervisor)

    supervisor.start()
    tray = TrayApp(supervisor, on_open_status=status_window.open)
    tray.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
