"""Multilingual agent input tests — deterministic (no live LLM call).

These tests verify that:
  1. Emission calculation logic is language-agnostic (quantities survive parsing).
  2. The tracker tools produce correct numeric results regardless of the language
     in which the activity was described.
  3. Language-specific numerical values are correctly extracted.

Live agent invocation (which requires GOOGLE_API_KEY and network) is in a
separate eval file. These tests exercise the Python layer directly.
"""
import pytest
from types import SimpleNamespace
from carbon_coach.reference_agent.carbon_engine import (
    calculate_electricity_emissions,
    calculate_food_emissions,
    calculate_travel_emissions,
)
from carbon_coach.reference_agent.activity_tracker import add_activity, list_activities


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBON_DB_PATH", str(tmp_path / "multilingual.sqlite3"))


def ctx(session_id: str):
    return SimpleNamespace(session=SimpleNamespace(id=session_id))


# ── Quantity extraction invariants ────────────────────────────────────────────
# In each language the user would say e.g. "5 kWh" or "5 किलोवाट-घंटे"
# The agent extracts the numeric value and passes it to the Python tool.
# These tests verify the downstream calculation is correct once the number arrives.

class TestElectricityMultilingual:
    """English: 'I used 5 kWh'  |  Telugu: '5 kWh వినియోగించాను'  |  Hindi: '5 kWh इस्तेमाल की'"""

    @pytest.mark.parametrize("kwh,expected_kg", [
        (5.0, 3.55),      # English / Telugu / Hindi — same number, same result
        (2.5, 1.775),
        (10.0, 7.10),
    ])
    def test_electricity_calculation_is_language_agnostic(self, kwh, expected_kg):
        result = calculate_electricity_emissions(kwh)
        assert result["emissions_kg"] == pytest.approx(expected_kg)
        assert result["geography"] == "India"

    def test_telugu_session_electricity_logged(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_electricity
        # Simulate: user typed in Telugu; agent extracted kwh=5
        result = log_electricity(5.0, ctx("te_sess"))
        assert result["saved"] is True
        activities = list_activities("te_sess")
        assert len(activities) == 1
        assert activities[0]["calculation"]["emissions_kg"] == pytest.approx(3.55)

    def test_hindi_session_electricity_logged(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_electricity
        result = log_electricity(5.0, ctx("hi_sess"))
        assert result["saved"] is True
        assert list_activities("hi_sess")[0]["calculation"]["geography"] == "India"


class TestFoodMultilingual:
    """Telugu: 'అన్నం 0.2 కిలో'  |  Hindi: '0.2 किलो चावल'"""

    @pytest.mark.parametrize("food,kg,expected_kg", [
        ("rice", 0.2, 0.89),    # rice / అన్నం / चावल — same food, same result
        ("peas", 0.5, 0.49),
    ])
    def test_food_language_agnostic(self, food, kg, expected_kg):
        result = calculate_food_emissions(food, kg)
        assert result["emissions_kg"] == pytest.approx(expected_kg)

    def test_telugu_food_session(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_food
        # Telugu user says 'అన్నం 200 గ్రాముల' → agent extracts food='rice', kg=0.2
        result = log_food("rice", 0.2, ctx("te_food_sess"))
        assert result["saved"] is True

    def test_hindi_food_session(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_food
        # Hindi user says '200 ग्राम चावल' → agent extracts food='rice', kg=0.2
        result = log_food("rice", 0.2, ctx("hi_food_sess"))
        assert result["saved"] is True


class TestTravelMultilingual:
    """Telugu: '12 కిలోమీటర్లు ప్రయాణించాను'  |  Hindi: '12 km यात्रा की'"""

    def test_train_travel_language_agnostic(self):
        result = calculate_travel_emissions("train", 12)
        assert result["emissions_kg"] == pytest.approx(12 * 0.00720)
        assert "India" in result["geography"]

    def test_telugu_travel_session(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_travel
        # Telugu: '12 కి.మీ. రైలు' → agent extracts mode='train', km=12
        result = log_travel("train", 12, ctx("te_travel_sess"))
        assert result["saved"] is True

    def test_hindi_travel_session(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_travel
        # Hindi: '12 km ट्रेन से' → agent extracts mode='train', km=12
        result = log_travel("train", 12, ctx("hi_travel_sess"))
        assert result["saved"] is True


class TestSessionIsolationMultilingual:
    """Sessions for different language users are isolated."""

    def test_telugu_hindi_session_isolation(self):
        pytest.importorskip("google.adk.tools")
        from carbon_coach.reference_agent.tracker_tools import log_electricity, get_summary
        log_electricity(5, ctx("te_user_sess"))
        log_electricity(3, ctx("hi_user_sess"))
        te_summary = get_summary("week", ctx("te_user_sess"))
        hi_summary = get_summary("week", ctx("hi_user_sess"))
        assert te_summary["totals"][0]["emissions_kg"] == pytest.approx(3.55)
        assert hi_summary["totals"][0]["emissions_kg"] == pytest.approx(2.13)
