"""Launcher entry point — wires supervisor, tray, and status window together."""

from __future__ import annotations

import os
import sys

from bsky_saves.cli import main as bsky_saves_main

from bsky_saves_launcher.status_window import StatusWindow
from bsky_saves_launcher.supervisor import Supervisor
from bsky_saves_launcher.tray import TrayApp

HELPER_ARGV = ["serve", "--gui"]


def _run_probe() -> None:
    """Print diagnostic info about the bundled Python environment.

    Triggered by setting BSKY_SAVES_PROBE=1 in the env when launching the
    .app's stub binary from a terminal. Output goes to stdout (captured by
    the terminal that launched the stub). Used to gather data for
    cross-environment bug triage (see tenorune/bsky-saves#19).
    """
    import json

    info: dict[str, object] = {}
    info["python_version"] = sys.version
    info["sys_executable"] = sys.executable
    info["sys_prefix"] = sys.prefix
    info["platform"] = sys.platform

    try:
        import httpx

        info["httpx_version"] = httpx.__version__
    except Exception as exc:
        info["httpx_version_error"] = repr(exc)

    try:
        import ssl

        info["openssl_version"] = ssl.OPENSSL_VERSION
    except Exception as exc:
        info["openssl_version_error"] = repr(exc)

    try:
        import httpx

        resp = httpx.get("https://tls.peet.ws/api/all", timeout=10.0)
        tls = resp.json().get("tls", {})
        info["ja3_hash"] = tls.get("ja3_hash")
        info["ja4"] = tls.get("ja4")
    except Exception as exc:
        info["ja3_error"] = repr(exc)

    print("=== BSKY_SAVES_PROBE ===")
    print(json.dumps(info, indent=2, default=str))
    print("=== /BSKY_SAVES_PROBE ===")


def main() -> int:
    if os.environ.get("BSKY_SAVES_PROBE"):
        _run_probe()
        return 0

    supervisor = Supervisor(target=bsky_saves_main, args=(HELPER_ARGV,))
    status_window = StatusWindow(supervisor)

    supervisor.start()
    tray = TrayApp(supervisor, on_open_status=status_window.open)
    tray.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
