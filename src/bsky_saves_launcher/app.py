"""Launcher entry point — wires supervisor, tray, and status window together."""

from __future__ import annotations

import os
import ssl
import sys

# TLS workaround for tenorune/bsky-saves#19 — AWS WAF rejects requests from the
# bundled Python's OpenSSL 3.0.x default TLS handshake (JA3
# 304734bb1c086c3453b387400cf83f11). Tweaking the SSLContext's cipher list,
# ALPN, or TLS-version range changes the JA3 and may flip the WAF result.
#
# Configurable via env vars so we can iterate without rebuilding:
#   BSKY_SAVES_TLS_CIPHERS — colon-separated OpenSSL cipher list; if set,
#       overrides the default cipher list on every SSLContext.
#   BSKY_SAVES_TLS_NO_HTTP2 — if truthy, only advertise http/1.1 in ALPN.
#   BSKY_SAVES_TLS_TLS12_ONLY — if truthy, cap maximum_version at TLSv1_2.
#   BSKY_SAVES_TLS_DEBUG — if truthy, print the configured SSLContext params
#       once on first use.
#
# Default values experimentally chosen to differ from the WAF-blocked JA3.
# Tweak via env var if the default doesn't flip the result.
_DEFAULT_CIPHERS = (
    "TLS_AES_128_GCM_SHA256:TLS_CHACHA20_POLY1305_SHA256:TLS_AES_256_GCM_SHA384:"
    "ECDHE-RSA-CHACHA20-POLY1305:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384:"
    "ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384"
)


def _install_tls_workaround() -> None:
    """Patch ssl.create_default_context so all SSLContexts get our customization.

    Must run BEFORE httpx/httpcore import or build their default SSLContext.
    """
    ciphers = os.environ.get("BSKY_SAVES_TLS_CIPHERS", _DEFAULT_CIPHERS).strip()
    no_h2 = bool(os.environ.get("BSKY_SAVES_TLS_NO_HTTP2"))
    tls12_only = bool(os.environ.get("BSKY_SAVES_TLS_TLS12_ONLY"))
    debug = bool(os.environ.get("BSKY_SAVES_TLS_DEBUG"))

    orig_create = ssl.create_default_context

    def patched(*args, **kwargs):
        ctx = orig_create(*args, **kwargs)
        if ciphers:
            try:
                ctx.set_ciphers(ciphers)
            except ssl.SSLError as exc:
                if debug:
                    print(f"[TLS workaround] set_ciphers failed: {exc!r}", file=sys.stderr)
        if no_h2:
            try:
                ctx.set_alpn_protocols(["http/1.1"])
            except Exception as exc:
                if debug:
                    print(f"[TLS workaround] set_alpn_protocols failed: {exc!r}", file=sys.stderr)
        if tls12_only:
            try:
                ctx.maximum_version = ssl.TLSVersion.TLSv1_2
            except Exception as exc:
                if debug:
                    print(f"[TLS workaround] tls12 cap failed: {exc!r}", file=sys.stderr)
        if debug:
            print(
                f"[TLS workaround] applied: ciphers={ciphers[:60]}... "
                f"no_h2={no_h2} tls12_only={tls12_only}",
                file=sys.stderr,
            )
        return ctx

    ssl.create_default_context = patched


# Defense-in-depth as of v0.1.3: kept always-on even though bsky-saves >= 0.6.6
# ships its own bsky_ssl_context() with a similar cipher reorder + certifi
# loaded. The helper-side context is passed as verify=ctx to httpx at each
# call site, which overrides our default-context patch at those sites — so
# the two layers don't fight. If bsky-saves ever adds a code path that
# constructs httpx without verify=bsky_ssl_context(), our launcher patch
# still gives it a WAF-friendly cipher list by default. Disable via
# BSKY_SAVES_TLS_DISABLE=1. See docs/v0.1-lessons.md and
# tenorune/bsky-saves#19 for the full history.
if not os.environ.get("BSKY_SAVES_TLS_DISABLE"):
    _install_tls_workaround()

from bsky_saves.cli import main as bsky_saves_main  # noqa: E402

from bsky_saves_launcher.status_window import StatusWindow  # noqa: E402
from bsky_saves_launcher.supervisor import Supervisor  # noqa: E402
from bsky_saves_launcher.tray import TrayApp  # noqa: E402

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

    # Compare against bsky-saves' own SSLContext, if v0.6.5+ bundles it. This
    # tells us whether the helper-side TLS workaround produces a different JA3
    # at all — and if so, whether it matches the JA3 the installer-side
    # workaround uses. Diagnostic for tenorune/bsky-saves#19.
    try:
        import httpx
        from bsky_saves._net import bsky_ssl_context  # type: ignore[import-not-found]

        ctx = bsky_ssl_context()
        info["bsky_ctx_ciphers"] = [c["name"] for c in ctx.get_ciphers()][:10]
        resp = httpx.get(
            "https://tls.peet.ws/api/all",
            verify=ctx,
            timeout=10.0,
        )
        tls = resp.json().get("tls", {})
        info["bsky_ctx_ja3_hash"] = tls.get("ja3_hash")
        info["bsky_ctx_ja4"] = tls.get("ja4")
    except ImportError as exc:
        info["bsky_ctx_unavailable"] = repr(exc)
    except Exception as exc:
        info["bsky_ctx_error"] = repr(exc)

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

        # Same bookmark fetch, but through bsky-saves' own SSLContext if it
        # exists. Tells us whether the helper-side cipher fix actually
        # produces a WAF-accepted JA3 when applied directly to a bookmark
        # call. For tenorune/bsky-saves#19.
        try:
            import httpx
            from bsky_saves._net import bsky_ssl_context  # type: ignore[import-not-found]

            ctx = bsky_ssl_context()
            r = httpx.get(
                "https://bsky.social/xrpc/app.bsky.bookmark.getBookmarks",
                params={"limit": 1},
                headers={"Authorization": f"Bearer {jwt}"},
                verify=ctx,
                timeout=30.0,
            )
            info["bookmark_with_bsky_ctx_status"] = r.status_code
            info["bookmark_with_bsky_ctx_headers"] = dict(r.headers)
            info["bookmark_with_bsky_ctx_body"] = r.text[:600]
        except ImportError:
            pass
        except Exception as exc:
            info["bookmark_with_bsky_ctx_error"] = repr(exc)
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
