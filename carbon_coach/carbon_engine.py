"""Deterministic calculation functions; independent of Gemini and ADK.

All functions return plain Python dicts suitable for JSON serialisation.
No quantities are ever inferred from Gemini output here; every result must
be reproducible from the same inputs without any LLM call.
"""
from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from .emission_factors import FACTORS, get_factor


# ── Internal helpers ──────────────────────────────────────────────────────────

def _parse_quantity(value: Any) -> Decimal:
    """Parse *value* into a non-negative finite Decimal, raising ValueError on bad input."""
    if isinstance(value, bool):
        raise ValueError("Quantity must be a nonnegative finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Quantity must be a nonnegative finite number") from None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("Quantity must be a nonnegative finite number")
    if not number.is_finite() or number < 0:
        raise ValueError("Quantity must be a nonnegative finite number")
    return number


# ── Core calculation ──────────────────────────────────────────────────────────

def calculate(category: str, factor_id: str, quantity: float) -> dict:
    """Calculate emissions for a known (category, factor_id) pair.

    Returns a dict containing the result and full source metadata so that every
    number is traceable to its published reference.

    Raises:
        ValueError: if the factor is unknown or quantity is invalid.
    """
    factor = get_factor(category, factor_id)   # raises ValueError if missing
    amount = _parse_quantity(quantity)
    value = Decimal(factor["value"])
    result = amount * value

    # Determine emissions unit from factor unit string
    emissions_unit = "kg CO2" if "/kWh" in factor["unit"] and "CO2e" not in factor["unit"] else "kg CO2e"
    if "CO2/" in factor["unit"] and "CO2e" not in factor["unit"]:
        emissions_unit = "kg CO2"
    elif "CO2e" in factor["unit"]:
        emissions_unit = "kg CO2e"

    return {
        "category": category,
        "factor_id": factor_id,
        "quantity": float(amount),
        "factor_value": float(value),
        "factor_unit": factor["unit"],
        "emissions_kg": float(result),
        "emissions_unit": emissions_unit,
        "geography": factor["geography"],
        "version": factor["version"],
        "boundary": factor["boundary"],
        "source": factor["source"],
        "notes": factor.get("notes", ""),
    }


# ── Convenience wrappers ──────────────────────────────────────────────────────

def calculate_electricity_emissions(kwh: float) -> dict:
    """Calculate India FY 2024-25 grid electricity CO2 for *kwh* consumed.

    Never infers kWh from appliance type or usage hours alone.
    """
    return calculate("electricity", "india_grid_fy2024_25", kwh)


_TRAVEL_MODE_MAP: dict[str, str] = {
    # Aliases → canonical factor_id
    "uk_bus": "uk_average_local_bus_2025",
    "uk_average_local_bus": "uk_average_local_bus_2025",
    "uk_average_local_bus_2025": "uk_average_local_bus_2025",
    "motorcycle": "india_two_wheeler_petrol",
    "two_wheeler": "india_two_wheeler_petrol",
    "scooter": "india_two_wheeler_petrol",
    "bike": "india_two_wheeler_petrol",
    "india_two_wheeler_petrol": "india_two_wheeler_petrol",
    "car": "india_car_petrol",
    "india_car_petrol": "india_car_petrol",
    "train": "india_train_average",
    "india_train_average": "india_train_average",
    "walking": "walking",
    "walk": "walking",
    "cycling": "cycling",
    "cycle": "cycling",
    "bicycle": "cycling",
}

_UNSUPPORTED_MODES = {
    # Modes users commonly request but for which no verified factor is configured
    "bus", "indian_bus", "india_bus", "autorickshaw", "metro",
    "flight", "plane", "airplane", "ferry", "boat",
}


def calculate_travel_emissions(mode: str, km: float) -> dict:
    """Calculate travel emissions for a supported transport mode and distance.

    Modes: uk_bus, car, motorcycle/scooter, train, walking, cycling.

    Raises:
        ValueError: if mode is unsupported or not yet configured.
    """
    normalised = mode.strip().lower().replace(" ", "_").replace("-", "_")

    if normalised in _UNSUPPORTED_MODES:
        raise ValueError(
            f"No verified emission factor is configured for '{mode}'. "
            "For Indian buses, no peer-reviewed national reference is currently "
            "loaded. Only uk_bus (UK reference scenario), car, motorcycle, train, "
            "walking, and cycling are supported. Please use one of those or ask "
            "the agent for a foreign-reference disclaimer."
        )

    factor_id = _TRAVEL_MODE_MAP.get(normalised)
    if factor_id is None:
        raise ValueError(
            f"Transport mode '{mode}' is not supported. "
            f"Available modes: {sorted(_TRAVEL_MODE_MAP.keys())}"
        )

    return calculate("travel", factor_id, km)


def calculate_food_emissions(food: str, kg: float) -> dict:
    """Calculate food supply-chain CO2e from kilograms of a supported food.

    Supported foods: rice, poultry, peas, wheat, beef, tofu, milk, eggs.

    Raises:
        ValueError: if the food type is not in the factor registry.
    """
    food_id = food.strip().lower()
    return calculate("food", food_id, kg)


def calculate_appliance_kwh(watts: float, hours: float) -> dict:
    """Convert appliance power and duration to kWh (deterministic energy conversion).

    Returns a dict with the result; does NOT compute emissions automatically,
    because that requires an explicit user-provided or consented emission factor.

    Formula: kWh = watts × hours / 1000
    """
    w = _parse_quantity(watts)
    h = _parse_quantity(hours)
    if h > Decimal("24"):
        raise ValueError("Hours per day cannot exceed 24")
    kwh = (w * h) / Decimal("1000")
    return {
        "watts": float(w),
        "hours": float(h),
        "kwh": float(kwh),
        "formula": "kWh = watts × hours / 1000",
        "note": (
            "This converts power and duration to energy. "
            "To compute emissions, pass the kWh result to calculate_electricity_emissions."
        ),
    }


# ── Comparison / what-if ──────────────────────────────────────────────────────

def calculate_reduction(
    category: str,
    original_factor_id: str,
    alternative_factor_id: str,
    quantity: float,
) -> dict:
    """Compare emissions of two sourced factors with the same unit and boundary.

    Returns the saving (positive = alternative is lower-emission).

    Raises:
        ValueError: if factors have different units, boundaries, or are unknown.
    """
    original = calculate(category, original_factor_id, quantity)
    alternative = calculate(category, alternative_factor_id, quantity)

    if original["factor_unit"] != alternative["factor_unit"]:
        raise ValueError(
            "Cannot compare factors with different units: "
            f"'{original['factor_unit']}' vs '{alternative['factor_unit']}'"
        )
    if original["boundary"] != alternative["boundary"]:
        raise ValueError(
            "Cannot compare factors with different accounting boundaries: "
            f"'{original['boundary']}' vs '{alternative['boundary']}'"
        )

    saving = original["emissions_kg"] - alternative["emissions_kg"]
    return {
        "original": original,
        "alternative": alternative,
        "saving_kg": round(saving, 9),
        "emissions_unit": original["emissions_unit"],
        "note": "Positive saving_kg means the alternative has lower estimated emissions",
    }


def calculate_travel_comparison(
    original_mode: str,
    alternative_mode: str,
    km: float,
) -> dict:
    """Compare emissions of two travel modes for the same distance.

    Raises:
        ValueError: if modes are unsupported or have incompatible units/boundaries.
    """
    original = calculate_travel_emissions(original_mode, km)
    alternative = calculate_travel_emissions(alternative_mode, km)

    if original["factor_unit"] != alternative["factor_unit"]:
        raise ValueError(
            "Cannot directly compare modes with different factor units: "
            f"'{original['factor_unit']}' vs '{alternative['factor_unit']}'. "
            "Different accounting boundaries may also make addition misleading."
        )

    saving = original["emissions_kg"] - alternative["emissions_kg"]
    return {
        "original_mode": original_mode,
        "alternative_mode": alternative_mode,
        "km": float(_parse_quantity(km)),
        "original": original,
        "alternative": alternative,
        "saving_kg": round(saving, 9),
        "emissions_unit": original["emissions_unit"],
        "note": "Positive saving_kg means the alternative mode has lower estimated emissions for the same distance",
    }
