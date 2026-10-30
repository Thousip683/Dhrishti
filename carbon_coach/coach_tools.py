"""Coach tools: session summaries, food comparison, travel what-if, recommendations.

All numerical estimates come from deterministic calculation functions.
Gemini never invents a saving figure; it calls these tools and reports the result.
"""
from __future__ import annotations

from google.adk.tools import ToolContext

from .activity_tracker import get_summary_data
from .carbon_engine import calculate_reduction, calculate_travel_comparison
from .recommendations import get_recommendations, what_if_food, what_if_travel


def coach_summary(period: str, tool_context: ToolContext) -> dict:
    """Read this session's actual recorded emissions for 'today', 'week', 'month', or 'all'.

    Always call this before making recommendations — never assume what the user logged.
    """
    try:
        return get_summary_data(tool_context.session.id, period)
    except ValueError as e:
        return {"error": str(e)}


def compare_food_options(
    original_food: str,
    alternative_food: str,
    kg: float,
) -> dict:
    """Compare equal masses of two supported foods using sourced supply-chain factors.

    Supported foods: rice, poultry, peas, wheat, beef, tofu, milk, eggs.
    Returns saving_kg and boundary metadata. Equal mass ≠ nutritionally equivalent.

    Args:
        original_food:   The food being replaced (e.g. 'poultry').
        alternative_food: The alternative food (e.g. 'peas').
        kg:              Mass in kilograms for both sides of the comparison.
    """
    try:
        result = what_if_food(original_food, alternative_food, kg)
        return result
    except ValueError as e:
        return {"error": str(e)}


def compare_travel_what_if(
    original_mode: str,
    alternative_mode: str,
    km: float,
) -> dict:
    """Compare CO₂e of two supported travel modes for the same distance.

    Returns original, alternative, and verified saving_kg.
    Both modes must share the same factor unit and accounting boundary.

    Supported modes: uk_bus, car, motorcycle, train, walking, cycling.
    """
    try:
        return what_if_travel(original_mode, alternative_mode, km)
    except ValueError as e:
        return {"error": str(e)}


def get_personalised_recommendations(tool_context: ToolContext) -> dict:
    """Generate personalised emission-reduction recommendations from this session's logged data.

    All numerical savings are verified by deterministic tools.
    Qualitative suggestions are returned where computation is not possible.
    """
    try:
        recs = get_recommendations(session_id=tool_context.session.id, period="week")
        return {"recommendations": recs}
    except Exception as e:
        return {"error": str(e)}
