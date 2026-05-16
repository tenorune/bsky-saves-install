"""Unit tests for scripts/fetch_wheel.py."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make scripts/ importable in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_wheel  # noqa: E402


WHEEL_BYTES = b"fake-wheel-contents"
WHEEL_SHA = hashlib.sha256(WHEEL_BYTES).hexdigest()


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_fetch_and_verify_success(tmp_path: Path) -> None:
    version_file = tmp_path / "wheel-version.txt"
    version_file.write_text("0.7.0\n")
    sha_file = tmp_path / "wheel.sha256"
    sha_file.write_text(WHEEL_SHA + "\n")
    wheelhouse = tmp_path / "wheelhouse"

    with patch.object(fetch_wheel.httpx, "get", return_value=FakeResponse(WHEEL_BYTES)):
        wheel_path = fetch_wheel.fetch(
            version_file=version_file,
            sha_file=sha_file,
            wheelhouse=wheelhouse,
            url_override="https://example.test/bsky_saves-0.7.0-py3-none-any.whl",
        )

    assert wheel_path.exists()
    assert wheel_path.read_bytes() == WHEEL_BYTES
    assert wheel_path.name == "bsky_saves-0.7.0-py3-none-any.whl"


def test_fetch_aborts_on_sha_mismatch(tmp_path: Path) -> None:
    version_file = tmp_path / "wheel-version.txt"
    version_file.write_text("0.7.0\n")
    sha_file = tmp_path / "wheel.sha256"
    sha_file.write_text("0" * 64 + "\n")
    wheelhouse = tmp_path / "wheelhouse"

    with patch.object(fetch_wheel.httpx, "get", return_value=FakeResponse(WHEEL_BYTES)):
        with pytest.raises(fetch_wheel.WheelVerificationError):
            fetch_wheel.fetch(
                version_file=version_file,
                sha_file=sha_file,
                wheelhouse=wheelhouse,
                url_override="https://example.test/bsky_saves-0.7.0-py3-none-any.whl",
            )

    assert not wheelhouse.exists() or not any(wheelhouse.iterdir())
