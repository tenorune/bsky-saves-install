"""Unit tests for the status snapshot fetch + parse + format pipeline."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import httpx

from bsky_saves_launcher.status import (
    HydrationProgress,
    LastActivity,
    LibraryInfo,
    StatusSnapshot,
    fetch_status,
    format_hydration_rows,
    format_last_activity,
    format_retention,
    format_staleness,
    format_total_saves,
)

# --- fetch_status -----------------------------------------------------------


def _resp(status_code, payload=None):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    if payload is not None:
        resp.json.return_value = payload
    return resp


def test_fetch_status_returns_none_on_404():
    with patch("bsky_saves_launcher.status.httpx.get", return_value=_resp(404)):
        assert fetch_status(token="abc") is None


def test_fetch_status_returns_none_on_network_error():
    with patch(
        "bsky_saves_launcher.status.httpx.get",
        side_effect=httpx.ConnectError("nope"),
    ):
        assert fetch_status(token="abc") is None


def test_fetch_status_returns_none_on_malformed_json():
    resp = _resp(200)
    resp.json.side_effect = ValueError("invalid")
    with patch("bsky_saves_launcher.status.httpx.get", return_value=resp):
        assert fetch_status(token="abc") is None


def test_fetch_status_sends_bearer_token():
    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        return _resp(404)

    with patch("bsky_saves_launcher.status.httpx.get", side_effect=fake_get):
        fetch_status(token="my-token")

    assert captured["headers"]["Authorization"] == "Bearer my-token"


def test_fetch_status_parses_full_payload():
    payload = {
        "schema_version": 1,
        "updated_at": "2026-05-17T20:15:00Z",
        "current_state": "idle",
        "library": {
            "handle": "alice.bsky.social",
            "did": "did:plc:abc123",
            "total_saves": 1247,
            "by_status": {"synced": 1230, "lost": 15, "unsaved": 2},
        },
        "hydration": {
            "articles": {"completed": 973, "total": 1247},
            "threads": {"completed": 412, "total": 1247},
            "images": {"completed": 856, "total": 1247},
        },
        "storage": {
            "mode": "persist",
            "session_ttl_seconds": None,
            "browser_bytes_estimate": 18234567,
        },
        "last_activity": {
            "kind": "fetch",
            "started_at": "2026-05-17T20:13:11Z",
            "finished_at": "2026-05-17T20:15:00Z",
            "added": 3,
            "removed": 0,
            "errors": [],
        },
    }
    with patch("bsky_saves_launcher.status.httpx.get", return_value=_resp(200, payload)):
        snap = fetch_status(token="abc")

    assert snap is not None
    assert snap.schema_version == 1
    assert snap.current_state == "idle"
    assert snap.library.handle == "alice.bsky.social"
    assert snap.library.total_saves == 1247
    assert snap.library.by_status == {"synced": 1230, "lost": 15, "unsaved": 2}
    assert snap.hydration["articles"] == HydrationProgress(completed=973, total=1247)
    assert snap.storage.mode == "persist"
    assert snap.last_activity.kind == "fetch"
    assert snap.last_activity.errors == []


def test_fetch_status_parses_minimal_payload_handle_only():
    payload = {
        "schema_version": 1,
        "updated_at": "2026-05-17T20:15:00Z",
        "library": {"handle": "alice.bsky.social"},
    }
    with patch("bsky_saves_launcher.status.httpx.get", return_value=_resp(200, payload)):
        snap = fetch_status(token="abc")

    assert snap is not None
    assert snap.library.handle == "alice.bsky.social"
    assert snap.library.total_saves is None
    assert snap.hydration == {}
    assert snap.storage is None
    assert snap.last_activity is None


def test_fetch_status_ignores_unknown_fields():
    payload = {
        "schema_version": 99,
        "updated_at": "2026-05-17T20:15:00Z",
        "future_field": {"some": "thing"},
        "library": {"handle": "alice.bsky.social", "experimental_count": 42},
    }
    with patch("bsky_saves_launcher.status.httpx.get", return_value=_resp(200, payload)):
        snap = fetch_status(token="abc")
    assert snap is not None
    assert snap.schema_version == 99
    assert snap.library.handle == "alice.bsky.social"


# --- format_total_saves -----------------------------------------------------


def test_format_total_saves_with_thousands_separator():
    snap = StatusSnapshot(library=LibraryInfo(total_saves=1247))
    assert format_total_saves(snap) == "1,247 saves"


def test_format_total_saves_singular():
    snap = StatusSnapshot(library=LibraryInfo(total_saves=1))
    assert format_total_saves(snap) == "1 save"


def test_format_total_saves_none_when_absent():
    assert format_total_saves(StatusSnapshot()) is None
    assert format_total_saves(StatusSnapshot(library=LibraryInfo())) is None


# --- format_retention -------------------------------------------------------


def test_format_retention_omits_zero_values():
    snap = StatusSnapshot(
        library=LibraryInfo(by_status={"synced": 1230, "lost": 15, "unsaved": 2})
    )
    # synced is the healthy default; only lost + unsaved render
    assert format_retention(snap) == "15 lost · 2 unsaved"


def test_format_retention_none_when_all_zero():
    snap = StatusSnapshot(
        library=LibraryInfo(by_status={"synced": 1247, "lost": 0, "unsaved": 0})
    )
    assert format_retention(snap) is None


def test_format_retention_handles_partial_dict():
    snap = StatusSnapshot(library=LibraryInfo(by_status={"lost": 3}))
    assert format_retention(snap) == "3 lost"


# --- format_hydration_rows --------------------------------------------------


def test_format_hydration_rows_filters_missing():
    snap = StatusSnapshot(
        hydration={
            "articles": HydrationProgress(completed=973, total=1247),
            "images": HydrationProgress(completed=856, total=1247),
        }
    )
    rows = format_hydration_rows(snap)
    # Order is stable: articles, threads, images. Threads absent → skipped.
    assert rows == [
        ("Articles", 973, 1247),
        ("Images", 856, 1247),
    ]


def test_format_hydration_rows_empty():
    assert format_hydration_rows(StatusSnapshot()) == []


# --- format_last_activity ---------------------------------------------------


def test_format_last_activity_fetch_basic():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="fetch",
            finished_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC),
            added=3,
            removed=0,
            errors=[],
        )
    )
    assert format_last_activity(snap, now=now) == "Fetch · 2 min ago · +3 / −0"


def test_format_last_activity_hydrate_articles():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="hydrate_articles",
            finished_at=dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC),
            added=0,
            removed=0,
            errors=[],
        )
    )
    # Hydrate-* labels: humanize the kind, no add/remove since they're 0/0
    assert format_last_activity(snap, now=now) == "Hydrate articles · just now"


def test_format_last_activity_none_when_absent():
    assert format_last_activity(StatusSnapshot(), now=dt.datetime.now(dt.UTC)) is None


# --- format_staleness -------------------------------------------------------


def test_format_staleness_none_under_threshold():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        updated_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC)
    )
    # 2 minutes ago — under 5-min threshold
    assert format_staleness(snap, now=now) is None


def test_format_staleness_minutes():
    now = dt.datetime(2026, 5, 17, 20, 27, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        updated_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC)
    )
    # 12 minutes
    assert format_staleness(snap, now=now) == "last seen 12 min ago"


def test_format_staleness_hours():
    now = dt.datetime(2026, 5, 17, 23, 15, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        updated_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC)
    )
    # 3 hours
    assert format_staleness(snap, now=now) == "last seen 3 h ago"


def test_format_staleness_days():
    now = dt.datetime(2026, 5, 19, 20, 15, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        updated_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC)
    )
    # 2 days
    assert format_staleness(snap, now=now) == "last seen 2 days ago"
