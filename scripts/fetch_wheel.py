"""Download a pinned bsky-saves wheel from PyPI and verify its SHA-256.

Reads `wheel-version.txt` and `wheel.sha256` from the repo root, downloads
`bsky_saves-{version}-py3-none-any.whl` from PyPI, verifies the SHA, and
places the wheel in `wheelhouse/`. Aborts on mismatch.

Run as a module: `python scripts/fetch_wheel.py`
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import httpx


PYPI_JSON_TEMPLATE = "https://pypi.org/pypi/bsky-saves/{version}/json"


class WheelVerificationError(RuntimeError):
    """Raised when a downloaded wheel's SHA-256 does not match the pin."""


def _resolve_wheel_url(version: str) -> str:
    """Resolve the canonical wheel URL via PyPI's JSON API."""
    resp = httpx.get(PYPI_JSON_TEMPLATE.format(version=version), timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    for url in data.get("urls", []):
        if url.get("packagetype") == "bdist_wheel" and url.get("filename", "").endswith(".whl"):
            return url["url"]
    raise WheelVerificationError(f"No wheel found on PyPI for bsky-saves=={version}")


def fetch(
    version_file: Path,
    sha_file: Path,
    wheelhouse: Path,
    *,
    url_override: str | None = None,
) -> Path:
    """Download + verify + place. Returns the path to the verified wheel."""
    version = version_file.read_text().strip()
    expected_sha = sha_file.read_text().strip().lower()
    if len(expected_sha) != 64:
        raise WheelVerificationError(
            f"Invalid SHA-256 in {sha_file}: expected 64 hex chars, got {len(expected_sha)}"
        )

    url = url_override or _resolve_wheel_url(version)
    resp = httpx.get(url, timeout=120.0)
    resp.raise_for_status()
    content = resp.content

    actual_sha = hashlib.sha256(content).hexdigest()
    if actual_sha != expected_sha:
        raise WheelVerificationError(
            f"SHA-256 mismatch for bsky-saves=={version}: "
            f"expected {expected_sha}, got {actual_sha}"
        )

    wheelhouse.mkdir(parents=True, exist_ok=True)
    wheel_path = wheelhouse / f"bsky_saves-{version}-py3-none-any.whl"
    wheel_path.write_bytes(content)
    return wheel_path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    try:
        wheel = fetch(
            version_file=root / "wheel-version.txt",
            sha_file=root / "wheel.sha256",
            wheelhouse=root / "wheelhouse",
        )
    except WheelVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Verified wheel: {wheel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
