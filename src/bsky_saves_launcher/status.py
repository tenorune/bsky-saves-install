"""Status snapshot from the helper's GET /status endpoint.

Wire and payload defined by the cross-repo contract at
tenorune/bsky-saves-coordination:docs/installer-status-panel.md
(section 4.2 endpoint, 4.4 payload, 4.5 panel-side surface).

This module owns the data layer: HTTP fetch + tolerant JSON parse +
display-format helpers. The popover side (popover.py) consumes
StatusSnapshot directly and only handles AppKit rendering.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import httpx

STATUS_TIMEOUT_S = 2.0
STALENESS_THRESHOLD_S = 300  # 5 minutes, locked by R10

_HYDRATION_ORDER = ("threads", "images", "articles")
# Past-tense verb phrases for the last-activity line. Render reads as
# "Last: <phrase> <time>" — e.g. "Last: fetched 2 min ago", "Last:
# backed up threads just now". Hydrate kinds are written as "backed up
# X" because that's what the user perceives — the GUI calls it hydration
# internally but the panel surface is for the end-user.
# "idle" maps to None: when nothing meaningful has happened we just hide
# the last-activity line entirely rather than rendering "Last: idle".
_KIND_LABELS: dict[str, str | None] = {
    "fetch": "fetched",
    "hydrate_articles": "backed up articles",
    "hydrate_threads": "backed up threads",
    "hydrate_images": "backed up images",
    "manual_refresh": "manually refreshed",
    "idle": None,
}


@dataclass(frozen=True)
class HydrationProgress:
    """Progress for a single hydration channel (articles/threads/images)."""

    completed: int
    total: int


@dataclass(frozen=True)
class LibraryInfo:
    """Identity + counts for the connected library."""

    handle: str | None = None
    did: str | None = None
    total_saves: int | None = None
    by_status: dict[str, int] | None = None


@dataclass(frozen=True)
class StorageInfo:
    """Storage backend metadata."""

    mode: str | None = None
    session_ttl_seconds: int | None = None
    browser_bytes_estimate: int | None = None


@dataclass(frozen=True)
class ErrorEntry:
    """A single error bucket emitted by the helper."""

    kind: str
    message: str
    count: int


@dataclass(frozen=True)
class LastActivity:
    """Most recent helper activity (fetch / hydrate / manual_refresh)."""

    kind: str | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    added: int = 0
    removed: int = 0
    errors: list[ErrorEntry] = field(default_factory=list)


@dataclass(frozen=True)
class StatusSnapshot:
    """A single read of the helper's GET /status payload, parsed tolerantly."""

    schema_version: int | None = None
    updated_at: dt.datetime | None = None
    current_state: str | None = None
    priority: str | None = None
    # Asymmetry note: `library` is always-present per the contract, so bad
    # input degrades to an empty LibraryInfo (never None). `storage` and
    # `last_activity` are optional per the contract, so bad input → None.
    library: LibraryInfo = field(default_factory=LibraryInfo)
    hydration: dict[str, HydrationProgress] = field(default_factory=dict)
    storage: StorageInfo | None = None
    last_activity: LastActivity | None = None


# --- fetch + parse ----------------------------------------------------------


def fetch_status(
    *, token: str, base_url: str = "http://127.0.0.1:47826"
) -> StatusSnapshot | None:
    """GET /status with bearer auth. Returns None on 404 or any error."""
    url = f"{base_url}/status"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=STATUS_TIMEOUT_S)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        payload = resp.json()
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return _parse_snapshot(payload)
    except Exception:
        return None


def _safe_int(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return None


def _safe_str(v: Any) -> str | None:
    if isinstance(v, str):
        return v
    return None


def _parse_iso(v: Any) -> dt.datetime | None:
    if not isinstance(v, str):
        return None
    try:
        # Python 3.11+ fromisoformat handles "Z" suffix.
        parsed = dt.datetime.fromisoformat(v)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed


def _parse_library(raw: Any) -> LibraryInfo:
    if not isinstance(raw, dict):
        return LibraryInfo()
    by_status_raw = raw.get("by_status")
    by_status: dict[str, int] | None = None
    if isinstance(by_status_raw, dict):
        by_status = {
            k: v
            for k, v in by_status_raw.items()
            if isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool)
        }
    return LibraryInfo(
        handle=_safe_str(raw.get("handle")),
        did=_safe_str(raw.get("did")),
        total_saves=_safe_int(raw.get("total_saves")),
        by_status=by_status,
    )


def _parse_hydration(raw: Any) -> dict[str, HydrationProgress]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, HydrationProgress] = {}
    for key, val in raw.items():
        if not isinstance(key, str) or not isinstance(val, dict):
            continue
        completed = _safe_int(val.get("completed"))
        total = _safe_int(val.get("total"))
        if completed is None or total is None:
            continue
        out[key] = HydrationProgress(completed=completed, total=total)
    return out


def _parse_storage(raw: Any) -> StorageInfo | None:
    if not isinstance(raw, dict):
        return None
    return StorageInfo(
        mode=_safe_str(raw.get("mode")),
        session_ttl_seconds=_safe_int(raw.get("session_ttl_seconds")),
        browser_bytes_estimate=_safe_int(raw.get("browser_bytes_estimate")),
    )


def _parse_errors(raw: Any) -> list[ErrorEntry]:
    if not isinstance(raw, list):
        return []
    out: list[ErrorEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind = _safe_str(item.get("kind"))
        message = _safe_str(item.get("message"))
        count = _safe_int(item.get("count"))
        if kind is None or message is None or count is None:
            continue
        out.append(ErrorEntry(kind=kind, message=message, count=count))
    return out


def _parse_last_activity(raw: Any) -> LastActivity | None:
    if not isinstance(raw, dict):
        return None
    return LastActivity(
        kind=_safe_str(raw.get("kind")),
        started_at=_parse_iso(raw.get("started_at")),
        finished_at=_parse_iso(raw.get("finished_at")),
        added=_safe_int(raw.get("added")) or 0,
        removed=_safe_int(raw.get("removed")) or 0,
        errors=_parse_errors(raw.get("errors")),
    )


def _parse_snapshot(payload: dict[str, Any]) -> StatusSnapshot:
    return StatusSnapshot(
        schema_version=_safe_int(payload.get("schema_version")),
        updated_at=_parse_iso(payload.get("updated_at")),
        current_state=_safe_str(payload.get("current_state")),
        priority=_safe_str(payload.get("priority")),
        library=_parse_library(payload.get("library")),
        hydration=_parse_hydration(payload.get("hydration")),
        storage=_parse_storage(payload.get("storage")),
        last_activity=_parse_last_activity(payload.get("last_activity")),
    )


# --- format helpers ---------------------------------------------------------


def format_total_saves(snap: StatusSnapshot) -> str | None:
    """Return "N saves" / "1 save" with thousands separator, or None if absent."""
    n = snap.library.total_saves
    if n is None:
        return None
    if n == 1:
        return "1 save"
    return f"{n:,} saves"


def format_retention(snap: StatusSnapshot) -> str | None:
    """Return "N lost · M unsaved" omitting zero/missing entries, None if all zero."""
    by_status = snap.library.by_status
    if not by_status:
        return None
    parts: list[str] = []
    for key in ("lost", "unsaved"):
        n = by_status.get(key, 0)
        if isinstance(n, int) and n > 0:
            parts.append(f"{n} {key}")
    if not parts:
        return None
    return " · ".join(parts)


def format_hydration_rows(snap: StatusSnapshot) -> list[tuple[str, int, int]]:
    """Return [(Label, completed, total), ...] in stable order, skipping missing."""
    rows: list[tuple[str, int, int]] = []
    for key in _HYDRATION_ORDER:
        prog = snap.hydration.get(key)
        if prog is None:
            continue
        rows.append((key.title(), prog.completed, prog.total))
    return rows


def _relative_time(then: dt.datetime, now: dt.datetime) -> str:
    delta = (now - then).total_seconds()
    if delta < 0:
        delta = 0
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)} min ago"
    if delta < 86400:
        return f"{int(delta // 3600)} h ago"
    if delta < 7 * 86400:
        days = int(delta // 86400)
        return f"{days} day ago" if days == 1 else f"{days} days ago"
    return then.date().isoformat()


def hydration_is_progressing(prev: StatusSnapshot | None, curr: StatusSnapshot) -> bool:
    """True iff any hydration channel's `completed` increased between two
    snapshots. Used by the panel to detect active hydration when the GUI's
    `current_state` doesn't flip to `"hydrating"` (observed in practice;
    GUI marks kind="idle" between transitions even mid-hydration).
    """
    if prev is None:
        return False
    for key in _HYDRATION_ORDER:
        p = prev.hydration.get(key)
        c = curr.hydration.get(key)
        if p is None or c is None:
            continue
        if c.completed > p.completed:
            return True
    return False


def format_last_activity(
    snap: StatusSnapshot, *, now: dt.datetime | None = None
) -> str | None:
    """Return a "Last: <verb-phrase> <time>" line, or None if absent.

    The label uses a past-tense verb phrase ("fetched", "backed up
    threads") so reading it inline produces "Last: fetched 2 min ago"
    or "Last: backed up images just now". `_KIND_LABELS` maps the
    contract kinds; unrecognized kinds fall through to a humanized
    form.

    Time source: `last_activity.finished_at` is preferred; if absent
    (the GUI sometimes omits it mid-activity) we fall back to
    `last_activity.started_at`. If neither is present, the verb phrase
    renders without a relative time.

    Returns None when:
      - `last_activity` is absent entirely;
      - `kind` is None or "idle" (no meaningful activity to report).

    In-flight states (`current_state == "refreshing"` / `"hydrating"`)
    are NOT handled here — the popover renderer composes the live
    label from `current_state` + observed hydration deltas; this
    function only describes the last *completed* activity.
    """
    la = snap.last_activity
    if la is None or la.kind is None:
        return None
    label = _KIND_LABELS.get(la.kind)
    if label is None and la.kind in _KIND_LABELS:
        # Explicit None in the map (e.g. "idle") → no rendering.
        return None
    if label is None:
        # Unknown kind: humanize fallback.
        label = la.kind.replace("_", " ").lower()
    if now is None:
        now = dt.datetime.now(dt.UTC)
    when_source = la.finished_at or la.started_at
    when = _relative_time(when_source, now) if when_source else None
    line = f"Last: {label}"
    if when:
        line += f" {when}"
    if la.added or la.removed:
        line += f" · +{la.added} / −{la.removed}"
    return line


def format_staleness(
    snap: StatusSnapshot, *, now: dt.datetime | None = None
) -> str | None:
    """Return "last seen N ago" if snap.updated_at is older than the threshold."""
    if snap.updated_at is None:
        return None
    if now is None:
        now = dt.datetime.now(dt.UTC)
    delta = (now - snap.updated_at).total_seconds()
    if delta < STALENESS_THRESHOLD_S:
        return None
    return f"last seen {_relative_time(snap.updated_at, now)}"
