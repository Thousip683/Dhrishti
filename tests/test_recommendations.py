"""Tests for the recommendation engine.

All numerical savings must come from verified tool calls — no fabricated values.
Tests check determinism, edge cases, and qualitative fallback behaviour.
"""
import pytest
from carbon_coach.recommendations import (
    get_recommendations,
    what_if_food,
    what_if_travel,
)
from carbon_coach.activity_tracker import add_activity
from carbon_coach.carbon_engine import (
    calculate_electricity_emissions,
    calculate_food_emissions,
    calculate_travel_emissions,
)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBON_DB_PATH", str(tmp_path / "recs.sqlite3"))


# ── what_if_food ──────────────────────────────────────────────────────────────

class TestWhatIfFood:
    def test_poultry_to_peas(self):
        r = what_if_food("poultry", "peas", 0.2)
        assert r["saving_kg"] == pytest.approx(1.778)
        assert r["saving_kg"] > 0
        assert "caveat" in r

    def test_beef_to_tofu(self):
        r = what_if_food("beef", "tofu", 1.0)
        assert r["saving_kg"] > 0

    def test_unsupported_food_raises(self):
        with pytest.raises(ValueError):
            what_if_food("mystery_burger", "peas", 0.2)

    def test_same_food_saving_zero(self):
        r = what_if_food("rice", "rice", 1.0)
        assert r["saving_kg"] == pytest.approx(0.0)

    def test_lower_emission_food_negative_saving(self):
        # Switching from peas (lower) to poultry (higher) gives negative saving
        r = what_if_food("peas", "poultry", 0.2)
        assert r["saving_kg"] < 0


# ── what_if_travel ────────────────────────────────────────────────────────────

class TestWhatIfTravel:
    def test_car_to_train(self):
        r = what_if_travel("car", "train", 10)
        assert r["saving_kg"] > 0

    def test_car_to_walking(self):
        r = what_if_travel("car", "walking", 5)
        # walking = 0 emissions, so saving = car emissions for 5km
        assert r["saving_kg"] == pytest.approx(5 * 0.1693)

    def test_motorcycle_to_cycling(self):
        r = what_if_travel("motorcycle", "cycling", 5)
        assert r["saving_kg"] > 0

    def test_unsupported_mode_raises(self):
        with pytest.raises(ValueError):
            what_if_travel("flight", "train", 500)


# ── get_recommendations ───────────────────────────────────────────────────────

class TestGetRecommendations:
    def test_no_activities_returns_start_logging_tip(self):
        recs = get_recommendations(session_id="empty_sess")
        assert len(recs) >= 1
        assert any("log" in r["title"].lower() or "start" in r["title"].lower() for r in recs)

    def test_electricity_activities_generate_recs(self):
        add_activity("sess1", calculate_electricity_emissions(10))
        recs = get_recommendations(session_id="sess1")
        assert any("electricity" in r["title"].lower() for r in recs)

    def test_car_activities_generate_train_rec(self):
        add_activity("sess1", calculate_travel_emissions("car", 20))
        recs = get_recommendations(session_id="sess1")
        assert any("train" in r["title"].lower() for r in recs)

    def test_motorcycle_generates_cycling_rec(self):
        add_activity("sess1", calculate_travel_emissions("motorcycle", 10))
        recs = get_recommendations(session_id="sess1")
        assert any("cycl" in r["title"].lower() or "cycling" in r["explanation"].lower() for r in recs)

    def test_poultry_generates_legume_rec(self):
        add_activity("sess1", calculate_food_emissions("poultry", 0.3))
        recs = get_recommendations(session_id="sess1")
        assert any("poultry" in r["title"].lower() or "pea" in r["explanation"].lower() for r in recs)

    def test_beef_generates_tofu_rec(self):
        add_activity("sess1", calculate_food_emissions("beef", 0.5))
        recs = get_recommendations(session_id="sess1")
        assert any("beef" in r["title"].lower() or "plant" in r["title"].lower() for r in recs)

    def test_verified_recommendations_have_tool_flag(self):
        add_activity("sess1", calculate_food_emissions("poultry", 0.3))
        recs = get_recommendations(session_id="sess1")
        verified = [r for r in recs if r["verified_by_tool"]]
        # At least one recommendation should be tool-verified
        assert len(verified) >= 1
        for r in verified:
            assert r["estimated_saving_kg"] is not None

    def test_all_recs_have_required_fields(self):
        add_activity("sess1", calculate_electricity_emissions(5))
        recs = get_recommendations(session_id="sess1")
        required = {"title", "explanation", "confidence", "verified_by_tool", "factor_ids", "assumptions"}
        for r in recs:
            assert required.issubset(set(r.keys())), f"Missing fields in rec: {r}"

    def test_requires_user_or_session(self):
        with pytest.raises(ValueError):
            get_recommendations()   # neither user_id nor session_id
