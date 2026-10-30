"""ADK-visible Tracker tools — session-scoped via ToolContext.

Each tool:
  1. Accepts explicit user inputs.
  2. Calls a deterministic carbon_engine function.
  3. Persists via activity_tracker (session_id from ToolContext).
  4. Returns a plain dict (JSON-serialisable) — never raw ADK objects.

Tools never infer kWh from appliance descriptions or fabricate emission factors.
"""
from __future__ import annotations

from google.adk.tools import ToolContext

from .carbon_engine import (
    calculate_appliance_kwh,
    calculate_electricity_emissions,
    calculate_food_emissions,
    calculate_travel_emissions,
    calculate_travel_comparison,
)
from .activity_tracker import (
    add_activity,
    delete_activity,
    get_summary_data,
    list_activities,
)
from .emission_factors import list_factors


# ── Logging tools ─────────────────────────────────────────────────────────────

def log_electricity(
    kwh: float,
    tool_context: ToolContext,
    client_event_id: str = "",
) -> dict:
    """Calculate and save India grid electricity CO₂ for *kwh* consumed.

    Never infer kWh from appliance type or usage hours alone.
    Call appliance_to_kwh first if you only have watts and hours.

    Args:
        kwh: Kilowatt-hours consumed (must be ≥ 0).
        client_event_id: Optional idempotency key to prevent duplicate logging.
    """
    try:
        calc = calculate_electricity_emissions(kwh)
        return add_activity(
            tool_context.session.id,
            calc,
            client_event_id or None,
        )
    except ValueError as e:
        return {"error": str(e)}


def log_travel(
    mode: str,
    km: float,
    tool_context: ToolContext,
    client_event_id: str = "",
) -> dict:
    """Calculate and save travel CO₂e for a supported mode and distance.

    Supported modes: uk_bus, car, motorcycle/scooter, train, walking, cycling.
    'bus' (generic) is NOT supported — use 'uk_bus' only with explicit consent
    that this is a UK reference scenario, not an Indian bus factor.

    Args:
        mode: Transport mode string (see supported modes above).
        km:   Distance in kilometres (must be ≥ 0).
        client_event_id: Optional idempotency key.
    """
    try:
        calc = calculate_travel_emissions(mode, km)
        return add_activity(
            tool_context.session.id,
            calc,
            client_event_id or None,
        )
    except ValueError as e:
        return {"error": str(e)}


def log_food(
    food: str,
    kg: float,
    tool_context: ToolContext,
    client_event_id: str = "",
) -> dict:
    """Calculate and save food supply-chain CO₂e for *kg* of a supported food.

    Supported foods: rice, poultry, peas, wheat, beef, tofu, milk, eggs.
    Always request mass in kilograms; do not accept meal counts or portions.

    Args:
        food: Food name (case-insensitive).
        kg:   Mass in kilograms (must be ≥ 0).
        client_event_id: Optional idempotency key.
    """
    try:
        calc = calculate_food_emissions(food, kg)
        return add_activity(
            tool_context.session.id,
            calc,
            client_event_id or None,
        )
    except ValueError as e:
        return {"error": str(e)}


# ── Retrieval tools ────────────────────────────────────────────────────────────

def get_summary(period: str, tool_context: ToolContext) -> dict:
    """Return this session's emission totals for 'today', 'week', 'month', or 'all'.

    Totals are separated by gas type and accounting boundary.
    """
    try:
        return get_summary_data(tool_context.session.id, period)
    except ValueError as e:
        return {"error": str(e)}


def get_activities(period: str, tool_context: ToolContext) -> dict:
    """Return activity history for this session: 'today', 'week', 'month', or 'all'."""
    try:
        return {"activities": list_activities(tool_context.session.id, period)}
    except ValueError as e:
        return {"error": str(e)}


def remove_activity(activity_id: str, tool_context: ToolContext) -> dict:
    """Soft-delete an activity from this session (sets deleted_at).

    Only activities belonging to the current session can be deleted.
    """
    try:
        return delete_activity(activity_id, tool_context.session.id)
    except ValueError as e:
        return {"error": str(e)}


# ── Utility / informational tools ──────────────────────────────────────────────

def appliance_to_kwh(watts: float, hours: float) -> dict:
    """Convert appliance power (watts) and duration (hours) to kWh.

    Use this to convert an AC/fan/appliance specification before calling
    log_electricity. Never pass raw hours to log_electricity.

    Formula: kWh = watts × hours / 1000
    """
    try:
        return calculate_appliance_kwh(watts, hours)
    except ValueError as e:
        return {"error": str(e)}


def list_supported_factors(category: str = "") -> dict:
    """Return the set of supported emission factor IDs and their metadata.

    Args:
        category: Optional filter — 'electricity', 'travel', or 'food'.
    """
    try:
        return list_factors(category or None)
    except Exception as e:
        return {"error": str(e)}


def compare_travel_modes(
    original_mode: str,
    alternative_mode: str,
    km: float,
) -> dict:
    """Compare CO₂e of two supported travel modes for the same distance.

    Returns original emissions, alternative emissions, and verified saving_kg.
    Only modes with compatible factor units and boundaries can be compared.
    """
    try:
        return calculate_travel_comparison(original_mode, alternative_mode, km)
    except ValueError as e:
        return {"error": str(e)}
