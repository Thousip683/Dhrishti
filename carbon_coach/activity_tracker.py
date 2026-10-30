"""SQLite activity ledger with full field schema, idempotency, and correction support.

Storage design:
  - Per-user_id + session_id isolation.
  - Idempotency key (client_event_id) prevents duplicate logging on retries.
  - Timezone-aware timestamps (stored as ISO-8601 UTC strings).
  - Incompatible emissions (different unit/boundary) are kept in separate buckets.
  - Parameterised SQL throughout — no string interpolation of user data.
  - Configurable DB path via CARBON_DB_PATH env var.

The FastAPI developer should inject authenticated user_id from their auth middleware.
This module never treats a user-supplied string as a trusted identity on its own.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


# ── DB path resolution ────────────────────────────────────────────────────────

def db_path() -> str:
    """Return the configured SQLite database file path."""
    return os.environ.get(
        "CARBON_DB_PATH",
        str(Path(__file__).resolve().parent.parent / "carbon_activities.sqlite3"),
    )


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS activities (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL DEFAULT '',
    session_id       TEXT NOT NULL,
    client_event_id  TEXT,
    category         TEXT NOT NULL,
    factor_id        TEXT NOT NULL,
    details          TEXT NOT NULL,
    emissions_kg     REAL NOT NULL,
    emissions_unit   TEXT NOT NULL,
    boundary         TEXT NOT NULL,
    campus_group     TEXT,
    campus_opted_in  INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL,
    deleted_at       TEXT,
    UNIQUE(session_id, client_event_id)
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_act_user_time    ON activities(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_act_session_time ON activities(session_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_act_campus_group ON activities(campus_group, created_at)",
]


def connect() -> sqlite3.Connection:
    """Open (and initialise if necessary) the SQLite connection."""
    path = db_path()
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(_DDL)
    for idx in _INDEXES:
        con.execute(idx)
    return con


# ── Write operations ──────────────────────────────────────────────────────────

def add_activity(
    session_id: str,
    calculation: dict,
    client_event_id: str | None = None,
    user_id: str = "",
    campus_group: str | None = None,
    campus_opted_in: bool = False,
) -> dict:
    """Persist a validated calculation result as an activity record.

    Args:
        session_id:       ADK/caller session identifier (required, non-empty).
        calculation:      Output dict from carbon_engine.calculate_*.
        client_event_id:  Optional idempotency key; same key = deduplication.
        user_id:          Caller-provided identity (must be pre-authenticated by FastAPI).
        campus_group:     Optional campus group label (department/hostel id).
        campus_opted_in:  Whether the user consented to campus analytics.

    Returns:
        dict with keys: saved, duplicate, activity_id, calculation.

    Raises:
        ValueError: on blank session_id, blank client_event_id, or conflicting key.
        RuntimeError: if the DB insert fails unexpectedly.
    """
    if not session_id:
        raise ValueError("A session identifier is required")
    if client_event_id is not None and not str(client_event_id).strip():
        raise ValueError("client_event_id must be non-empty if provided")

    created = datetime.now(timezone.utc).isoformat()
    row_id = str(uuid4())

    row = (
        row_id, user_id, session_id, client_event_id,
        calculation["category"], calculation["factor_id"],
        json.dumps(calculation),
        calculation["emissions_kg"], calculation["emissions_unit"], calculation["boundary"],
        campus_group, int(campus_opted_in), created,
    )

    with connect() as con:
        cur = con.execute(
            """INSERT OR IGNORE INTO activities
               (id, user_id, session_id, client_event_id,
                category, factor_id, details,
                emissions_kg, emissions_unit, boundary,
                campus_group, campus_opted_in, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            row,
        )
        if cur.rowcount == 0:
            # Duplicate — look up existing record
            existing = con.execute(
                "SELECT * FROM activities WHERE session_id=? AND client_event_id=?",
                (session_id, client_event_id),
            ).fetchone()
            if not existing:
                raise RuntimeError("Failed to save activity (unknown DB error)")
            existing_calc = json.loads(existing["details"])
            # Detect conflicting use of the same idempotency key
            if (
                existing_calc.get("category") != calculation.get("category")
                or existing_calc.get("factor_id") != calculation.get("factor_id")
                or existing_calc.get("quantity") != calculation.get("quantity")
            ):
                raise ValueError(
                    f"client_event_id '{client_event_id}' already belongs to a different activity"
                )
            return {
                "saved": False,
                "duplicate": True,
                "activity_id": existing["id"],
                "calculation": existing_calc,
            }

    return {"saved": True, "duplicate": False, "activity_id": row_id, "calculation": calculation}


def delete_activity(activity_id: str, session_id: str) -> dict:
    """Soft-delete an activity record (sets deleted_at timestamp).

    Only the owning session may delete the record.

    Returns:
        dict with key 'deleted' (bool) and 'activity_id'.
    """
    if not activity_id or not session_id:
        raise ValueError("activity_id and session_id are required")
    deleted_at = datetime.now(timezone.utc).isoformat()
    with connect() as con:
        cur = con.execute(
            "UPDATE activities SET deleted_at=? WHERE id=? AND session_id=? AND deleted_at IS NULL",
            (deleted_at, activity_id, session_id),
        )
    return {"deleted": cur.rowcount > 0, "activity_id": activity_id}


# ── Read operations ───────────────────────────────────────────────────────────

def _cutoff_for_period(period: str, now: datetime) -> datetime | None:
    """Return the start-of-period datetime or None (meaning 'all time')."""
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    if period == "month":
        return now - timedelta(days=30)
    if period == "all":
        return None
    raise ValueError(f"period must be 'today', 'week', 'month', or 'all'; got '{period}'")


def list_activities(
    session_id: str,
    period: str = "all",
    now: datetime | None = None,
) -> list[dict]:
    """Return non-deleted activities for a session within the given period.

    Args:
        session_id: Session identifier (required).
        period:     'today' | 'week' | 'month' | 'all'.
        now:        Reference datetime (must be tz-aware); defaults to UTC now.

    Returns:
        List of dicts: {activity_id, created_at, calculation}.
    """
    if not session_id:
        raise ValueError("A session identifier is required")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include timezone info")
    now = now.astimezone(timezone.utc)
    cutoff = _cutoff_for_period(period, now)

    sql = "SELECT * FROM activities WHERE session_id=? AND deleted_at IS NULL"
    args: list[Any] = [session_id]
    if cutoff:
        sql += " AND created_at >= ? AND created_at <= ?"
        args.extend([cutoff.isoformat(), now.isoformat()])
    sql += " ORDER BY created_at, id"

    with connect() as con:
        rows = con.execute(sql, args).fetchall()

    return [
        {
            "activity_id": r["id"],
            "created_at": r["created_at"],
            "calculation": json.loads(r["details"]),
        }
        for r in rows
    ]


def list_activities_by_user(
    user_id: str,
    period: str = "all",
    now: datetime | None = None,
) -> list[dict]:
    """Return all non-deleted activities for a user across all sessions.

    The FastAPI layer must supply a pre-authenticated user_id.
    """
    if not user_id:
        raise ValueError("A user_id is required")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include timezone info")
    now = now.astimezone(timezone.utc)
    cutoff = _cutoff_for_period(period, now)

    sql = "SELECT * FROM activities WHERE user_id=? AND deleted_at IS NULL"
    args: list[Any] = [user_id]
    if cutoff:
        sql += " AND created_at >= ? AND created_at <= ?"
        args.extend([cutoff.isoformat(), now.isoformat()])
    sql += " ORDER BY created_at, id"

    with connect() as con:
        rows = con.execute(sql, args).fetchall()

    return [
        {
            "activity_id": r["id"],
            "session_id": r["session_id"],
            "created_at": r["created_at"],
            "calculation": json.loads(r["details"]),
        }
        for r in rows
    ]


def get_summary_data(
    session_id: str,
    period: str = "week",
    now: datetime | None = None,
) -> dict:
    """Aggregate recorded emissions into compatible buckets for a session.

    Totals are separated by (emissions_unit, boundary) pair to avoid
    mixing CO2 and CO2e or different accounting scopes.
    """
    activities = list_activities(session_id, period, now)
    # Keep distinct gas units AND accounting boundaries separate
    buckets: dict[tuple[str, str], float] = {}
    for activity in activities:
        c = activity["calculation"]
        key = (c["emissions_unit"], c["boundary"])
        buckets[key] = buckets.get(key, 0.0) + c["emissions_kg"]

    return {
        "period": period,
        "activity_count": len(activities),
        "totals": [
            {"emissions_unit": k[0], "boundary": k[1], "emissions_kg": round(v, 9)}
            for k, v in sorted(buckets.items())
        ],
        "note": (
            "Totals are separated by gas type and accounting boundary. "
            "They are not directly additive and do not represent a full lifecycle footprint."
        ),
    }


def get_summary_data_by_user(
    user_id: str,
    period: str = "week",
    now: datetime | None = None,
) -> dict:
    """Aggregate emissions across all sessions for an authenticated user."""
    activities = list_activities_by_user(user_id, period, now)
    buckets: dict[tuple[str, str], float] = {}
    for activity in activities:
        c = activity["calculation"]
        key = (c["emissions_unit"], c["boundary"])
        buckets[key] = buckets.get(key, 0.0) + c["emissions_kg"]

    return {
        "user_id": user_id,
        "period": period,
        "activity_count": len(activities),
        "totals": [
            {"emissions_unit": k[0], "boundary": k[1], "emissions_kg": round(v, 9)}
            for k, v in sorted(buckets.items())
        ],
        "note": (
            "Cross-session summary for authenticated user. "
            "Totals are separated by gas type and accounting boundary."
        ),
    }
