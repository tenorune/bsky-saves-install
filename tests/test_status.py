"""Unit tests for the status snapshot fetch + parse + format pipeline."""

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import httpx
import pytest

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
    hydration_is_progressing,
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
    # Order is stable: threads, images, articles. Threads absent → skipped.
    assert rows == [
        ("Images", 856, 1247),
        ("Articles", 973, 1247),
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
    assert format_last_activity(snap, now=now) == "Last: fetched 2 min ago · +3 / −0"


def test_format_last_activity_hydrate_threads():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="hydrate_threads",
            finished_at=dt.datetime(2026, 5, 17, 20, 16, 30, tzinfo=dt.UTC),
            added=0,
            removed=0,
            errors=[],
        )
    )
    assert format_last_activity(snap, now=now) == "Last: backed up threads just now"


def test_format_last_activity_hydrate_articles_minutes():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="hydrate_articles",
            finished_at=dt.datetime(2026, 5, 17, 20, 12, 0, tzinfo=dt.UTC),
            added=0,
            removed=0,
            errors=[],
        )
    )
    assert format_last_activity(snap, now=now) == "Last: backed up articles 5 min ago"


def test_format_last_activity_falls_back_to_started_at():
    """When finished_at is None but started_at is set, use started_at
    for the relative-time anchor. Covers the GUI's mid-activity push
    where finished_at hasn't been written yet."""
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="hydrate_images",
            started_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC),
            finished_at=None,
            added=0,
            removed=0,
            errors=[],
        )
    )
    assert format_last_activity(snap, now=now) == "Last: backed up images 2 min ago"


def test_format_last_activity_idle_kind_returns_none():
    """kind='idle' produces no rendering — there's no meaningful past
    activity to report."""
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="idle",
            finished_at=dt.datetime(2026, 5, 17, 20, 16, 0, tzinfo=dt.UTC),
            added=0,
            removed=0,
            errors=[],
        )
    )
    assert format_last_activity(snap, now=now) is None


def test_format_last_activity_none_when_absent():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    assert format_last_activity(StatusSnapshot(), now=now) is None


def test_format_last_activity_manual_refresh():
    now = dt.datetime(2026, 5, 17, 20, 17, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        last_activity=LastActivity(
            kind="manual_refresh",
            finished_at=dt.datetime(2026, 5, 17, 20, 16, 0, tzinfo=dt.UTC),
            added=2,
            removed=1,
            errors=[],
        )
    )
    assert (
        format_last_activity(snap, now=now)
        == "Last: manually refreshed 1 min ago · +2 / −1"
    )


# --- hydration_is_progressing -----------------------------------------------


def test_hydration_is_progressing_none_prev():
    assert hydration_is_progressing(None, StatusSnapshot()) is False


def test_hydration_is_progressing_detects_increase():
    prev = StatusSnapshot(
        hydration={"threads": HydrationProgress(completed=400, total=1247)}
    )
    curr = StatusSnapshot(
        hydration={"threads": HydrationProgress(completed=412, total=1247)}
    )
    assert hydration_is_progressing(prev, curr) is True


def test_hydration_is_progressing_no_change():
    snap = StatusSnapshot(
        hydration={"threads": HydrationProgress(completed=412, total=1247)}
    )
    assert hydration_is_progressing(snap, snap) is False


def test_hydration_is_progressing_decrease_returns_false():
    """`completed` going DOWN (e.g. user cleared) is not progress."""
    prev = StatusSnapshot(
        hydration={"threads": HydrationProgress(completed=412, total=1247)}
    )
    curr = StatusSnapshot(
        hydration={"threads": HydrationProgress(completed=0, total=1247)}
    )
    assert hydration_is_progressing(prev, curr) is False


def test_hydration_is_progressing_any_channel():
    """Increase on any single channel counts as progressing."""
    prev = StatusSnapshot(
        hydration={
            "threads": HydrationProgress(completed=412, total=1247),
            "images": HydrationProgress(completed=856, total=1247),
            "articles": HydrationProgress(completed=973, total=1247),
        }
    )
    curr = StatusSnapshot(
        hydration={
            "threads": HydrationProgress(completed=412, total=1247),
            "images": HydrationProgress(completed=856, total=1247),
            "articles": HydrationProgress(completed=980, total=1247),
        }
    )
    assert hydration_is_progressing(prev, curr) is True


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


def test_format_staleness_one_day():
    now = dt.datetime(2026, 5, 18, 20, 15, 0, tzinfo=dt.UTC)
    snap = StatusSnapshot(
        updated_at=dt.datetime(2026, 5, 17, 20, 15, 0, tzinfo=dt.UTC)
    )
    # Exactly 1 day
    assert format_staleness(snap, now=now) == "last seen 1 day ago"


# --- tolerant parser --------------------------------------------------------


@pytest.mark.parametrize(
    "bad_payload, description",
    [
        ([], "payload is a list, not a dict"),
        (None, "payload is None"),
        ("a string", "payload is a string"),
        ({"library": "not a dict"}, "library sub-object is wrong type"),
        ({"hydration": "broken"}, "hydration sub-object is wrong type"),
        ({"storage": []}, "storage sub-object is wrong type"),
        ({"last_activity": 42}, "last_activity sub-object is wrong type"),
        ({"library": {"total_saves": "1247"}}, "total_saves is string not int"),
        (
            {"library": {"total_saves": True}},
            "total_saves is bool — must be rejected (bool is int subclass)",
        ),
        ({"updated_at": "not-a-date"}, "malformed ISO-8601"),
        ({"library": {"by_status": "not a dict"}}, "by_status is wrong type"),
        (
            {"hydration": {"articles": "broken"}},
            "hydration entry value is wrong type",
        ),
        (
            {"hydration": {"articles": {"completed": "x", "total": "y"}}},
            "hydration entry fields are strings",
        ),
        ({"last_activity": {"errors": "not a list"}}, "errors is wrong type"),
        (
            {"last_activity": {"errors": [{"kind": 1, "message": 2, "count": "x"}]}},
            "error entry fields are wrong types",
        ),
    ],
)
def test_fetch_status_tolerates_bad_shapes(bad_payload, description):
    """Tolerant parser: bad shapes return None (for whole-payload-bad) or
    a snapshot with sensible defaults (for sub-object-bad). Never raises."""
    with patch(
        "bsky_saves_launcher.status.httpx.get",
        return_value=_resp(200, bad_payload),
    ):
        # Should never raise; result is either None or a usable StatusSnapshot.
        result = fetch_status(token="abc")
    # If payload isn't even a dict, fetch_status returns None.
    if not isinstance(bad_payload, dict):
        assert result is None, description
    else:
        # Bad sub-objects yield a snapshot with defaults; never crash.
        assert result is not None, description
