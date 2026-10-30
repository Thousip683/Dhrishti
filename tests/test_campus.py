"""Tests for campus aggregation engine.

All tests use an isolated SQLite database.
Verifies privacy suppression, opted-in filtering, and leaderboard ranking.
"""
import pytest
from carbon_coach.campus_analytics import (
    get_campus_summary,
    get_department_comparison,
    get_hostel_leaderboard,
)
from carbon_coach.activity_tracker import add_activity
from carbon_coach.carbon_engine import calculate_electricity_emissions


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBON_DB_PATH", str(tmp_path / "campus.sqlite3"))


def _add_opted_in(user_id: str, kwh: float, campus_group: str, sess: str = None):
    """Helper: add an opted-in electricity record for a user."""
    sess = sess or f"sess_{user_id}"
    add_activity(
        sess,
        calculate_electricity_emissions(kwh),
        user_id=user_id,
        campus_group=campus_group,
        campus_opted_in=True,
    )


def _add_opted_out(user_id: str, kwh: float, campus_group: str):
    """Helper: add a non-opted-in record."""
    add_activity(
        f"sess_{user_id}",
        calculate_electricity_emissions(kwh),
        user_id=user_id,
        campus_group=campus_group,
        campus_opted_in=False,
    )


# ── Campus summary ────────────────────────────────────────────────────────────

class TestCampusSummary:
    def test_privacy_suppressed_below_threshold(self):
        # Only 2 opted-in users; default threshold is 3
        _add_opted_in("u1", 5, "CampusA")
        _add_opted_in("u2", 3, "CampusA")
        result = get_campus_summary("CampusA", period="all", min_group_size=3)
        assert result["privacy_suppressed"] is True
        assert result["total_emissions_kg"] is None

    def test_campus_aggregate_above_threshold(self):
        _add_opted_in("u1", 5, "CampusB")
        _add_opted_in("u2", 3, "CampusB")
        _add_opted_in("u3", 2, "CampusB")
        result = get_campus_summary("CampusB", period="all", min_group_size=3)
        assert result["privacy_suppressed"] is False
        # 5+3+2 = 10 kWh × 0.71 = 7.1 kg CO2
        assert result["total_emissions_kg"] == pytest.approx(10 * 0.71, rel=1e-3)
        assert result["total_opted_in_users"] == 3

    def test_opted_out_records_excluded(self):
        _add_opted_in("u1", 5, "CampusC")
        _add_opted_in("u2", 3, "CampusC")
        _add_opted_in("u3", 2, "CampusC")
        _add_opted_out("u4", 100, "CampusC")  # this should NOT be counted
        result = get_campus_summary("CampusC", period="all", min_group_size=3)
        assert result["total_opted_in_users"] == 3
        # Only opted-in emissions
        assert result["total_emissions_kg"] == pytest.approx(10 * 0.71, rel=1e-3)

    def test_no_records_suppressed(self):
        result = get_campus_summary("EmptyCampus", period="all", min_group_size=1)
        assert result["privacy_suppressed"] is True   # 0 < 1
        assert result["total_opted_in_users"] == 0


# ── Department comparison ─────────────────────────────────────────────────────

class TestDepartmentComparison:
    def test_departments_aggregated_correctly(self):
        for i in range(3):
            _add_opted_in(f"u{i}", 5, "CampusD/CSE")
        for i in range(3):
            _add_opted_in(f"v{i}", 2, "CampusD/ECE")

        results = get_department_comparison("CampusD", ["CSE", "ECE"], period="all", min_group_size=3)
        assert len(results) == 2
        cse = next(r for r in results if "CSE" in r["group_id"])
        ece = next(r for r in results if "ECE" in r["group_id"])
        assert cse["total_emissions_kg"] == pytest.approx(3 * 5 * 0.71, rel=1e-3)
        assert ece["total_emissions_kg"] == pytest.approx(3 * 2 * 0.71, rel=1e-3)

    def test_small_department_suppressed(self):
        _add_opted_in("u1", 5, "CampusE/SmallDept")
        results = get_department_comparison("CampusE", ["SmallDept"], period="all", min_group_size=3)
        assert results[0]["privacy_suppressed"] is True

    def test_results_sorted_by_emissions(self):
        for i in range(3):
            _add_opted_in(f"a{i}", 10, "CampusF/HighEmit")
        for i in range(3):
            _add_opted_in(f"b{i}", 1, "CampusF/LowEmit")

        results = get_department_comparison("CampusF", ["HighEmit", "LowEmit"], period="all", min_group_size=3)
        # Higher emitters should come first
        assert results[0]["total_emissions_kg"] > results[1]["total_emissions_kg"]


# ── Hostel leaderboard ────────────────────────────────────────────────────────

class TestHostelLeaderboard:
    def test_ranked_by_per_participant_emissions(self):
        # Hostel A: 3 users, 5 kWh each → 5 kWh/person
        for i in range(3):
            _add_opted_in(f"ha{i}", 5, "CampusG/HostelA")
        # Hostel B: 3 users, 2 kWh each → 2 kWh/person (lower = rank 1)
        for i in range(3):
            _add_opted_in(f"hb{i}", 2, "CampusG/HostelB")

        result = get_hostel_leaderboard("CampusG", ["HostelA", "HostelB"], period="all", min_group_size=3)
        lb = result["leaderboard"]
        assert lb[0]["hostel_id"] == "HostelB"   # lower per-participant
        assert lb[0]["rank"] == 1
        assert lb[1]["rank"] == 2

    def test_small_hostel_excluded(self):
        for i in range(3):
            _add_opted_in(f"h{i}", 5, "CampusH/BigHostel")
        _add_opted_in("lonely", 100, "CampusH/SmallHostel")

        result = get_hostel_leaderboard("CampusH", ["BigHostel", "SmallHostel"], period="all", min_group_size=3)
        assert result["suppressed_groups"] == 1
        assert len(result["leaderboard"]) == 1

    def test_empty_leaderboard(self):
        result = get_hostel_leaderboard("CampusX", ["NoSuchHostel"], period="all", min_group_size=1)
        # No opted-in records at all
        assert result["leaderboard"] == [] or result["suppressed_groups"] >= 1

    def test_leaderboard_note_present(self):
        result = get_hostel_leaderboard("CampusY", [], period="week")
        assert "note" in result
        assert len(result["note"]) > 10
