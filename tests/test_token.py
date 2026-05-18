"""Unit tests for the pairing-token reader."""

from __future__ import annotations

from pathlib import Path

import pytest

from bsky_saves_launcher.token import read_pairing_token


def test_returns_token_when_file_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("abcdef0123456789abcdef0123456789\n")
    monkeypatch.setattr(
        "bsky_saves_launcher.token._token_path",
        lambda: token_file,
    )

    assert read_pairing_token() == "abcdef0123456789abcdef0123456789"


def test_strips_trailing_whitespace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("  abcdef  \n\n")
    monkeypatch.setattr(
        "bsky_saves_launcher.token._token_path",
        lambda: token_file,
    )

    assert read_pairing_token() == "abcdef"


def test_returns_none_when_file_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "bsky_saves_launcher.token._token_path",
        lambda: tmp_path / "does-not-exist",
    )

    assert read_pairing_token() is None


def test_returns_none_when_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("")
    monkeypatch.setattr(
        "bsky_saves_launcher.token._token_path",
        lambda: token_file,
    )

    assert read_pairing_token() is None


def test_returns_none_when_file_is_only_whitespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("   \n\n  \t  ")
    monkeypatch.setattr(
        "bsky_saves_launcher.token._token_path",
        lambda: token_file,
    )

    assert read_pairing_token() is None
