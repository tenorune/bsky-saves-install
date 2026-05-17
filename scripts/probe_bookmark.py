"""Direct bookmark-endpoint probe — diagnostic for tenorune/bsky-saves#19.

Mirrors the bookmark-probe path inside the bundled launcher's BSKY_SAVES_PROBE
(see src/bsky_saves_launcher/app.py::_run_probe) so the same data shape can be
captured from a non-bundled Python and compared.

Usage:
    BSKY_SAVES_PROBE_JWT=<fresh accessJwt> \
        /path/to/pip/python scripts/probe_bookmark.py

The JWT must be a Bluesky upstream accessJwt (NOT the bsky-saves pairing token).
Mint one via:

    import httpx
    r = httpx.post(
        "https://bsky.social/xrpc/com.atproto.server.createSession",
        json={"identifier": "you.bsky.social", "password": "xxxx-xxxx-xxxx-xxxx"},
        timeout=30.0,
    )
    print(r.json()["accessJwt"])

The JWT expires in ~2h — use a fresh one each run.
"""

from __future__ import annotations

import json
import os
import socket
import sys


def main() -> int:
    jwt = os.environ.get("BSKY_SAVES_PROBE_JWT")
    if not jwt:
        print("ERROR: set BSKY_SAVES_PROBE_JWT in the env first.", file=sys.stderr)
        return 1

    info: dict[str, object] = {}
    info["python_version"] = sys.version
    info["sys_executable"] = sys.executable
    info["sys_prefix"] = sys.prefix
    info["platform"] = sys.platform

    try:
        import httpx
    except ImportError:
        print("ERROR: httpx not installed in this Python.", file=sys.stderr)
        return 1

    import ssl

    info["httpx_version"] = httpx.__version__
    info["openssl_version"] = ssl.OPENSSL_VERSION

    try:
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

    url = "https://bsky.social/xrpc/app.bsky.bookmark.getBookmarks"
    try:
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

    print(json.dumps(info, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
