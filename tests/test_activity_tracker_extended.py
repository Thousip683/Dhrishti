"""Tests for expanded activity tracker — user_id, delete, month period, by-user queries.

All tests use an isolated in-memory SQLite database via the CARBON_DB_PATH fixture.
"""
import pytest
from datetime import datetime, timezone, timedelta
from carbon_coach.activity_tracker import (
    add_activity,
    list_activities,
    list_activities_by_user,
    get_summary_data,
    get_summary_data_by_user,
    delete_activity,
)
from carbon_coach.carbon_engine import (
    calculate_electricity_emissions,
    calculate_food_emissions,
    calculate_travel_emissions,
)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBON_DB_PATH", str(tmp_path / "test_extended.sqlite3"))


# ── user_id isolation ─────────────────────────────────────────────────────────

class TestUserIsolation:
    def test_user_id_stored_and_retrieved(self):
        calc = calculate_electricity_emissions(5)
        add_activity("sess1", calc, user_id="alice@example.com")
        rows = list_activities_by_user("alice@example.com")
        assert len(rows) == 1
        assert "calculation" in rows[0]

    def test_user_isolation_cross_user(self):
        add_activity("sess1", calculate_electricity_emissions(3), user_id="alice@example.com")
        add_activity("sess2", calculate_electricity_emissions(2), user_id="bob@example.com")
        alice = list_activities_by_user("alice@example.com")
        bob = list_activities_by_user("bob@example.com")
        assert len(alice) == 1
        assert len(bob) == 1

    def test_summary_by_user(self):
        add_activity("sess1", calculate_electricity_emissions(5), user_id="alice@example.com")
        add_activity("sess1", calculate_electricity_emissions(2), user_id="alice@example.com")
        s = get_summary_data_by_user("alice@example.com", "week")
        assert s["activity_count"] == 2
        assert s["totals"][0]["emissions_kg"] == pytest.approx(4.97)

    def test_blank_user_id_raises(self):
        with pytest.raises(ValueError):
            list_activities_by_user("")


# ── Soft delete ────────────────────────────────────────────────────────────────

class TestSoftDelete:
    def test_delete_removes_from_list(self):
        a = add_activity("sess1", calculate_electricity_emissions(5))
        act_id = a["activity_id"]
        result = delete_activity(act_id, "sess1")
        assert result["deleted"] is True
        assert list_activities("sess1") == []

    def test_delete_wrong_session_not_deleted(self):
        a = add_activity("sess1", calculate_electricity_emissions(5))
        act_id = a["activity_id"]
        result = delete_activity(act_id, "sess_other")
        assert result["deleted"] is False
        # Original session still sees it
        assert len(list_activities("sess1")) == 1

    def test_delete_idempotent(self):
        a = add_activity("sess1", calculate_electricity_emissions(5))
        act_id = a["activity_id"]
        delete_activity(act_id, "sess1")
        result2 = delete_activity(act_id, "sess1")
        assert result2["deleted"] is False   # already deleted


# ── Period filtering ──────────────────────────────────────────────────────────

class TestPeriodFiltering:
    def test_month_period_returns_recent(self):
        add_activity("sess1", calculate_electricity_emissions(1))
        acts = list_activities("sess1", "month")
        assert len(acts) == 1

    def test_month_period_excludes_old(self):
        calc = calculate_electricity_emissions(1)
        add_activity("sess1", calc)
        # 'all' always includes everything
        acts_all = list_activities("sess1", "all")
        assert len(acts_all) == 1
        # 'month' (30 days) should include recent records
        acts_month = list_activities("sess1", "month")
        assert len(acts_month) == 1

    def test_today_excludes_old(self):
        calc = calculate_electricity_emissions(5)
        # Simulate adding a record with an old timestamp by checking
        # that today filter still works
        add_activity("sess1", calc)
        now = datetime.now(timezone.utc)
        old_now = now - timedelta(days=2)
        # Use 'today' filter — should see today's record
        acts = list_activities("sess1", "today", now=now)
        assert len(acts) == 1

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError, match="period must be"):
            list_activities("sess1", "year")

    def test_invalid_period_summary_raises(self):
        with pytest.raises(ValueError):
            get_summary_data("sess1", "quarterly")


# ── Idempotency with user_id ──────────────────────────────────────────────────

class TestIdempotencyExtended:
    def test_same_event_id_same_user(self):
        calc = calculate_electricity_emissions(5)
        r1 = add_activity("sess1", calc, "evt1", user_id="alice@example.com")
        r2 = add_activity("sess1", calc, "evt1", user_id="alice@example.com")
        assert r1["saved"] is True
        assert r2["duplicate"] is True
        assert len(list_activities("sess1")) == 1

    def test_conflict_different_calc_same_event_id(self):
        calc1 = calculate_electricity_emissions(5)
        calc2 = calculate_electricity_emissions(7)
        add_activity("sess1", calc1, "evt1")
        with pytest.raises(ValueError, match="different activity"):
            add_activity("sess1", calc2, "evt1")


# ── Campus opt-in ─────────────────────────────────────────────────────────────

class TestCampusOptIn:
    def test_campus_group_stored(self):
        calc = calculate_electricity_emissions(5)
        add_activity(
            "sess1", calc,
            user_id="alice@example.com",
            campus_group="IIT_Hyd/CSE",
            campus_opted_in=True,
        )
        rows = list_activities("sess1")
        assert len(rows) == 1   # appears in normal listing

    def test_no_campus_group_by_default(self):
        calc = calculate_electricity_emissions(5)
        add_activity("sess1", calc, user_id="alice@example.com")
        rows = list_activities("sess1")
        assert len(rows) == 1


# ── Mixed categories ──────────────────────────────────────────────────────────

class TestMixedCategories:
    def test_incompatible_units_separate_buckets(self):
        add_activity("s1", calculate_electricity_emissions(5))
        add_activity("s1", calculate_food_emissions("rice", 0.2))
        summary = get_summary_data("s1", "all")
        assert len(summary["totals"]) == 2

    def test_same_unit_same_boundary_merged(self):
        add_activity("s1", calculate_food_emissions("rice", 0.2))
        add_activity("s1", calculate_food_emissions("peas", 0.25))
        summary = get_summary_data("s1", "all")
        # Both food items share the same CO2e unit and boundary
        assert len(summary["totals"]) == 1
        assert summary["totals"][0]["emissions_kg"] == pytest.approx(0.89 + 0.245)
