"""Service layer tests — CarbonCoachService (non-ADK paths).

Tests cover:
  - get_activities / get_summary / get_recommendations (deterministic)
  - Campus leaderboard (deterministic)
  - chat() is tested only when GOOGLE_API_KEY is set (marked as integration test)

Run deterministic tests with: pytest tests/test_service.py -m "not integration"
Run all tests with:           pytest tests/test_service.py
"""
import os
import pytest
from carbon_coach.reference_agent.service import CarbonCoachService
from carbon_coach.reference_agent.activity_tracker import add_activity
from carbon_coach.reference_agent.carbon_engine import (
    calculate_electricity_emissions,
    calculate_food_emissions,
    calculate_travel_emissions,
)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CARBON_DB_PATH", str(tmp_path / "service_test.sqlite3"))


@pytest.fixture
def service():
    return CarbonCoachService()


# ── get_activities ────────────────────────────────────────────────────────────

class TestGetActivities:
    def test_returns_empty_for_new_user(self, service):
        result = service.get_activities(user_id="newuser", session_id="sess1")
        assert result == []

    def test_session_activities_returned(self, service):
        add_activity("sess1", calculate_electricity_emissions(5))
        result = service.get_activities(user_id="alice", session_id="sess1")
        assert len(result) == 1
        assert "calculation" in result[0]

    def test_by_user_across_sessions(self, service):
        add_activity("sess1", calculate_electricity_emissions(5), user_id="alice")
        add_activity("sess2", calculate_electricity_emissions(3), user_id="alice")
        result = service.get_activities(user_id="alice")
        assert len(result) == 2


# ── get_summary ────────────────────────────────────────────────────────────────

class TestGetSummary:
    def test_empty_summary(self, service):
        s = service.get_summary("alice", "week", "empty_sess")
        assert s["activity_count"] == 0
        assert s["totals"] == []

    def test_summary_has_correct_total(self, service):
        add_activity("sess1", calculate_electricity_emissions(5))
        add_activity("sess1", calculate_electricity_emissions(2))
        s = service.get_summary("alice", "week", "sess1")
        assert s["activity_count"] == 2
        assert s["totals"][0]["emissions_kg"] == pytest.approx(4.97)

    def test_summary_note_present(self, service):
        s = service.get_summary("alice", "week", "sess1")
        assert "note" in s and len(s["note"]) > 5


# ── get_recommendations ───────────────────────────────────────────────────────

class TestGetRecommendations:
    def test_no_activities_returns_suggestions(self, service):
        recs = service.get_recommendations("alice", "empty_sess")
        assert isinstance(recs, list)
        assert len(recs) >= 1

    def test_electricity_activity_generates_rec(self, service):
        add_activity("sess1", calculate_electricity_emissions(10))
        recs = service.get_recommendations("alice", "sess1")
        assert any("electricity" in r["title"].lower() for r in recs)

    def test_recs_have_confidence_field(self, service):
        add_activity("sess1", calculate_food_emissions("poultry", 0.5))
        recs = service.get_recommendations("alice", "sess1")
        for r in recs:
            assert "confidence" in r
            assert r["confidence"] in ("high", "medium", "low")


# ── Campus methods ────────────────────────────────────────────────────────────

class TestCampusMethods:
    def _add_opted_in(self, user_id, kwh, campus_group, sess=None):
        add_activity(
            sess or f"sess_{user_id}",
            calculate_electricity_emissions(kwh),
            user_id=user_id,
            campus_group=campus_group,
            campus_opted_in=True,
        )

    def test_campus_summary_returns_dict(self, service):
        s = service.get_campus_summary("IIT_Hyd", "week")
        assert "campus_id" in s
        assert "period" in s

    def test_campus_leaderboard_returns_dict(self, service):
        for i in range(3):
            self._add_opted_in(f"u{i}", 5, "IIT_Hyd/HostelA")
        result = service.get_campus_leaderboard("IIT_Hyd", ["HostelA"], "all")
        assert "leaderboard" in result
        assert "note" in result

    def test_department_comparison_returns_list(self, service):
        result = service.get_department_comparison("IIT_Hyd", ["CSE", "ECE"], "all")
        assert isinstance(result, list)


# ── chat() integration tests ──────────────────────────────────────────────────

@pytest.mark.integration
class TestChatIntegration:
    """Requires GOOGLE_API_KEY to be set. Skipped if not available."""

    @pytest.fixture(autouse=True)
    def require_api_key(self):
        key = os.environ.get("GOOGLE_API_KEY", "")
        if not key or key == "PASTE_YOUR_KEY_HERE":
            pytest.skip("GOOGLE_API_KEY not set — skipping live agent test")

    @pytest.mark.asyncio
    async def test_chat_returns_reply(self, service):
        result = await service.chat(
            message="Hello, what can you help me with?",
            session_id="test_session_1",
            user_id="test_user",
        )
        assert "reply" in result
        assert len(result["reply"]) > 0
        assert result["session_id"] == "test_session_1"

    @pytest.mark.asyncio
    async def test_chat_logs_electricity(self, service):
        result = await service.chat(
            message="I used 5 kWh of electricity today. Please log it.",
            session_id="test_session_2",
            user_id="test_user",
        )
        assert "reply" in result
        assert "tool_calls_made" in result
        # Should have called log_electricity
        assert any("electric" in tc.lower() or "log" in tc.lower()
                   for tc in result["tool_calls_made"])

    @pytest.mark.asyncio
    async def test_chat_electricity_telugu(self, service):
        result = await service.chat(
            message="ఈరోజు నేను 5 kWh విద్యుత్ వినియోగించాను. దయచేసి లాగ్ చేయండి.",
            session_id="test_session_telugu",
            user_id="test_user_te",
            language="te",
        )
        assert "reply" in result
        assert len(result["reply"]) > 0

    @pytest.mark.asyncio
    async def test_chat_electricity_hindi(self, service):
        result = await service.chat(
            message="आज मैंने 5 kWh बिजली इस्तेमाल की। कृपया इसे लॉग करें।",
            session_id="test_session_hindi",
            user_id="test_user_hi",
            language="hi",
        )
        assert "reply" in result
        assert len(result["reply"]) > 0

    @pytest.mark.asyncio
    async def test_chat_blank_message_raises(self, service):
        with pytest.raises(ValueError):
            await service.chat("", "sess1", "user1")

    @pytest.mark.asyncio
    async def test_chat_blank_session_raises(self, service):
        with pytest.raises(ValueError):
            await service.chat("Hello", "", "user1")
