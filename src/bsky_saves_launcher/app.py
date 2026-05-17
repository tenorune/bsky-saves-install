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

    If BSKY_SAVES_PROBE_JWT is also set, the probe additionally calls
    https://bsky.social/xrpc/app.bsky.bookmark.getBookmarks with that JWT
    and dumps the response. Compare against the pip-Python output from
    scripts/probe_bookmark.py.
    """
    import json
    import socket

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

    info["env_http_proxy"] = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    info["env_https_proxy"] = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    info["env_no_proxy"] = os.environ.get("NO_PROXY") or os.environ.get("no_proxy")
    info["env_ssl_cert_file"] = os.environ.get("SSL_CERT_FILE")
    info["env_requests_ca_bundle"] = os.environ.get("REQUESTS_CA_BUNDLE")

    try:
        info["getaddrinfo_bsky"] = [
            {"family": str(t[0]), "addr": t[4]}
            for t in socket.getaddrinfo("bsky.social", 443, type=socket.SOCK_STREAM)
        ]
    except Exception as exc:
        info["getaddrinfo_error"] = repr(exc)

    jwt = os.environ.get("BSKY_SAVES_PROBE_JWT")
    if jwt:
        try:
            import httpx

            url = "https://bsky.social/xrpc/app.bsky.bookmark.getBookmarks"
            r = httpx.get(
                url,
                params={"limit": 1},
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=30.0,
            )
            info["bookmark_status"] = r.status_code
            info["bookmark_response_headers"] = dict(r.headers)
            info["bookmark_response_body"] = r.text[:1500]
            info["bookmark_request_headers"] = {
                k: ("<redacted>" if k.lower() == "authorization" else v)
                for k, v in r.request.headers.items()
            }
        except Exception as exc:
            info["bookmark_error"] = repr(exc)
    else:
        info["bookmark_probe"] = (
            "skipped — set BSKY_SAVES_PROBE_JWT to a fresh accessJwt to exercise"
        )

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
