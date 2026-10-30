"""Campus aggregation engine — Python-only, no HTTP.

Computes campus, department, and hostel emission summaries from opted-in
activity records. The FastAPI teammate exposes these through HTTP endpoints;
this module only contains pure Python logic.

Privacy design:
  - Only records where campus_opted_in = 1 are included in aggregates.
  - Groups with fewer than MIN_GROUP_SIZE opted-in participants are suppressed.
  - Individual user activities are never returned by this module.
  - Results use aggregated totals only.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .activity_tracker import connect
from .config import CAMPUS_MIN_GROUP_SIZE


# ── Internal helpers ──────────────────────────────────────────────────────────

def _rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _aggregate_rows(rows: list[dict]) -> dict[tuple[str, str], float]:
    """Bucket emissions by (emissions_unit, boundary), summing kg values."""
    buckets: dict[tuple[str, str], float] = {}
    for r in rows:
        details = json.loads(r["details"])
        key = (details["emissions_unit"], details["boundary"])
        buckets[key] = buckets.get(key, 0.0) + r["emissions_kg"]
    return buckets


def _primary_bucket(buckets: dict[tuple[str, str], float]) -> tuple[float, str, str]:
    """Return the largest bucket's (total_kg, unit, boundary)."""
    if not buckets:
        return 0.0, "kg CO2e", "unknown"
    (unit, boundary), total = max(buckets.items(), key=lambda x: x[1])
    return total, unit, boundary


def _period_sql_fragment(period: str) -> tuple[str, list]:
    """Return SQL WHERE fragment and args list for the requested period."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    if period == "today":
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    elif period == "all":
        return "", []
    else:
        raise ValueError(f"period must be today, week, month, or all; got '{period}'")
    return " AND created_at >= ? AND created_at <= ?", [cutoff.isoformat(), now.isoformat()]


# ── Public API ────────────────────────────────────────────────────────────────

def get_campus_summary(
    campus_id: str,
    period: str = "week",
    min_group_size: int | None = None,
) -> dict:
    """Return aggregated emissions for all opted-in users with the given campus_group.

    Args:
        campus_id:      The campus group label to aggregate (e.g. "IIT_Hyderabad").
        period:         'today' | 'week' | 'month' | 'all'.
        min_group_size: Override the configured minimum for privacy suppression.

    Returns:
        dict matching the CampusSummary schema.
    """
    threshold = min_group_size if min_group_size is not None else CAMPUS_MIN_GROUP_SIZE
    time_sql, time_args = _period_sql_fragment(period)

    with connect() as con:
        # Count distinct opted-in users
        user_rows = con.execute(
            f"""SELECT DISTINCT user_id FROM activities
                WHERE campus_group=? AND campus_opted_in=1
                  AND deleted_at IS NULL {time_sql}""",
            [campus_id] + time_args,
        ).fetchall()
        participant_count = len(user_rows)

        if participant_count < threshold:
            return {
                "campus_id": campus_id,
                "period": period,
                "total_opted_in_users": participant_count,
                "total_emissions_kg": None,
                "emissions_unit": None,
                "boundary": None,
                "groups": [],
                "privacy_suppressed": True,
                "note": (
                    f"Fewer than {threshold} participants opted in — "
                    "campus totals are suppressed to protect privacy."
                ),
            }

        # Aggregate emissions
        rows = con.execute(
            f"""SELECT details, emissions_kg FROM activities
                WHERE campus_group=? AND campus_opted_in=1
                  AND deleted_at IS NULL {time_sql}""",
            [campus_id] + time_args,
        ).fetchall()

    rows_dicts = [dict(r) for r in rows]
    buckets = _aggregate_rows(rows_dicts)
    total_kg, unit, boundary = _primary_bucket(buckets)

    return {
        "campus_id": campus_id,
        "period": period,
        "total_opted_in_users": participant_count,
        "total_emissions_kg": round(total_kg, 6),
        "emissions_unit": unit,
        "boundary": boundary,
        "groups": [],
        "privacy_suppressed": False,
        "note": (
            "Aggregated opted-in emissions only. "
            "Non-opted-in users are excluded. "
            "Individual activities are never exposed."
        ),
    }


def get_department_comparison(
    campus_id: str,
    departments: list[str],
    period: str = "week",
    min_group_size: int | None = None,
) -> list[dict]:
    """Return per-department emission aggregates, suppressing small groups.

    Args:
        campus_id:    Parent campus group label.
        departments:  List of department sub-group identifiers.
        period:       'today' | 'week' | 'month' | 'all'.
        min_group_size: Privacy threshold override.

    Returns:
        List of GroupEmissions-compatible dicts, one per department.
    """
    threshold = min_group_size if min_group_size is not None else CAMPUS_MIN_GROUP_SIZE
    time_sql, time_args = _period_sql_fragment(period)
    results = []

    for dept in departments:
        group_label = f"{campus_id}/{dept}"
        with connect() as con:
            user_rows = con.execute(
                f"""SELECT DISTINCT user_id FROM activities
                    WHERE campus_group=? AND campus_opted_in=1
                      AND deleted_at IS NULL {time_sql}""",
                [group_label] + time_args,
            ).fetchall()
            participant_count = len(user_rows)

            if participant_count < threshold:
                results.append({
                    "group_id": group_label,
                    "group_type": "department",
                    "participant_count": participant_count,
                    "total_emissions_kg": None,
                    "emissions_unit": None,
                    "boundary": None,
                    "period": period,
                    "privacy_suppressed": True,
                    "note": f"Fewer than {threshold} participants — suppressed.",
                })
                continue

            rows = con.execute(
                f"""SELECT details, emissions_kg FROM activities
                    WHERE campus_group=? AND campus_opted_in=1
                      AND deleted_at IS NULL {time_sql}""",
                [group_label] + time_args,
            ).fetchall()

        rows_dicts = [dict(r) for r in rows]
        buckets = _aggregate_rows(rows_dicts)
        total_kg, unit, boundary = _primary_bucket(buckets)

        results.append({
            "group_id": group_label,
            "group_type": "department",
            "participant_count": participant_count,
            "total_emissions_kg": round(total_kg, 6),
            "emissions_unit": unit,
            "boundary": boundary,
            "period": period,
            "privacy_suppressed": False,
            "note": "Opted-in participants only.",
        })

    # Sort by total_emissions_kg descending (suppressed groups go last)
    results.sort(
        key=lambda x: (x["privacy_suppressed"], -(x["total_emissions_kg"] or 0))
    )
    return results


def get_hostel_leaderboard(
    campus_id: str,
    hostels: list[str],
    period: str = "week",
    min_group_size: int | None = None,
) -> dict:
    """Return a ranked hostel leaderboard for opted-in emissions.

    Rankings are by total_emissions_kg per opted-in participant (lower = better).
    Groups with fewer than min_group_size participants are excluded from ranking.

    Returns:
        dict with 'campus_id', 'period', 'leaderboard' (list of ranked groups),
        'suppressed_groups' (count), 'note'.
    """
    threshold = min_group_size if min_group_size is not None else CAMPUS_MIN_GROUP_SIZE
    time_sql, time_args = _period_sql_fragment(period)
    ranked = []
    suppressed_count = 0

    for hostel in hostels:
        group_label = f"{campus_id}/{hostel}"
        with connect() as con:
            user_rows = con.execute(
                f"""SELECT DISTINCT user_id FROM activities
                    WHERE campus_group=? AND campus_opted_in=1
                      AND deleted_at IS NULL {time_sql}""",
                [group_label] + time_args,
            ).fetchall()
            participant_count = len(user_rows)

            if participant_count < threshold:
                suppressed_count += 1
                continue

            rows = con.execute(
                f"""SELECT details, emissions_kg FROM activities
                    WHERE campus_group=? AND campus_opted_in=1
                      AND deleted_at IS NULL {time_sql}""",
                [group_label] + time_args,
            ).fetchall()

        rows_dicts = [dict(r) for r in rows]
        buckets = _aggregate_rows(rows_dicts)
        total_kg, unit, boundary = _primary_bucket(buckets)
        per_participant = total_kg / participant_count if participant_count else 0.0

        ranked.append({
            "hostel_id": hostel,
            "group_id": group_label,
            "participant_count": participant_count,
            "total_emissions_kg": round(total_kg, 6),
            "emissions_per_participant_kg": round(per_participant, 6),
            "emissions_unit": unit,
            "boundary": boundary,
        })

    # Lower per-participant = better rank
    ranked.sort(key=lambda x: x["emissions_per_participant_kg"])
    for i, entry in enumerate(ranked, 1):
        entry["rank"] = i

    return {
        "campus_id": campus_id,
        "period": period,
        "leaderboard": ranked,
        "suppressed_groups": suppressed_count,
        "note": (
            "Ranked by emissions per opted-in participant (lower = lower footprint). "
            f"Groups with fewer than {threshold} opted-in participants are excluded. "
            "Rankings reflect only logged, opted-in activities — not total campus impact."
        ),
    }
