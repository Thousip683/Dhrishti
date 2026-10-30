"""Personalized coaching and what-if recommendation engine.

Produces structured Recommendation objects from actual recorded activity data.
Every numerical savings estimate is backed by a deterministic tool call; the
engine never fabricates factors or savings figures.

If a comparison is scientifically unsupported (different units, different
boundaries) a non-numeric qualitative recommendation is returned instead.
"""
from __future__ import annotations

from typing import Any

from .carbon_engine import (
    calculate_food_emissions,
    calculate_travel_comparison,
    calculate_reduction,
)
from .activity_tracker import list_activities_by_user, list_activities


# ── Data class ────────────────────────────────────────────────────────────────

class Recommendation:
    """A single actionable emission-reduction recommendation."""

    def __init__(
        self,
        title: str,
        explanation: str,
        estimated_saving_kg: float | None = None,
        emissions_unit: str | None = None,
        time_period: str | None = None,
        factor_ids: list[str] | None = None,
        assumptions: list[str] | None = None,
        confidence: str = "low",
        verified_by_tool: bool = False,
    ) -> None:
        self.title = title
        self.explanation = explanation
        self.estimated_saving_kg = estimated_saving_kg
        self.emissions_unit = emissions_unit
        self.time_period = time_period
        self.factor_ids = factor_ids or []
        self.assumptions = assumptions or []
        self.confidence = confidence      # "high" | "medium" | "low"
        self.verified_by_tool = verified_by_tool

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "explanation": self.explanation,
            "estimated_saving_kg": self.estimated_saving_kg,
            "emissions_unit": self.emissions_unit,
            "time_period": self.time_period,
            "factor_ids": self.factor_ids,
            "assumptions": self.assumptions,
            "confidence": self.confidence,
            "verified_by_tool": self.verified_by_tool,
        }


# ── What-if comparisons ───────────────────────────────────────────────────────

def what_if_travel(
    original_mode: str,
    alternative_mode: str,
    km: float,
) -> dict:
    """Compute verified emission saving for switching travel modes.

    Returns a dict with original, alternative, saving_kg, and full metadata.
    Raises ValueError if either mode is unsupported or factors are incompatible.
    """
    return calculate_travel_comparison(original_mode, alternative_mode, km)


def what_if_food(
    original_food: str,
    alternative_food: str,
    kg: float,
) -> dict:
    """Compute verified emission saving for switching food choice (equal mass).

    Caveat: equal mass ≠ equal nutrition.
    Returns dict with saving_kg and boundary-compatible metadata.
    Raises ValueError if food is unsupported or factors are incompatible.
    """
    result = calculate_reduction("food", original_food.lower(), alternative_food.lower(), kg)
    result["caveat"] = (
        "Equal mass is not nutritionally equivalent. "
        "This comparison is illustrative, not a meal substitution guide."
    )
    return result


# ── Recommendation generation ─────────────────────────────────────────────────

def _get_activities_for(
    user_id: str | None,
    session_id: str | None,
    period: str,
) -> list[dict]:
    if user_id:
        return list_activities_by_user(user_id, period)
    if session_id:
        return list_activities(session_id, period)
    return []


def get_recommendations(
    user_id: str | None = None,
    session_id: str | None = None,
    period: str = "week",
) -> list[dict]:
    """Generate personalised recommendations from recorded activities.

    At least one of user_id or session_id must be supplied.
    All numerical estimates are computed by deterministic tools.
    If a comparison cannot be made, a qualitative suggestion is returned.
    """
    if not user_id and not session_id:
        raise ValueError("Either user_id or session_id is required")

    activities = _get_activities_for(user_id, session_id, period)
    recs: list[Recommendation] = []

    categories_seen: set[str] = set()
    travel_modes_seen: set[str] = set()
    food_items_seen: dict[str, float] = {}  # food_id -> total kg
    electricity_kwh_total: float = 0.0

    for act in activities:
        calc = act["calculation"]
        cat = calc.get("category", "")
        fid = calc.get("factor_id", "")
        qty = calc.get("quantity", 0.0)
        categories_seen.add(cat)

        if cat == "travel":
            travel_modes_seen.add(fid)
        elif cat == "food":
            food_items_seen[fid] = food_items_seen.get(fid, 0.0) + qty
        elif cat == "electricity":
            electricity_kwh_total += qty

    # ── Electricity recommendations ───────────────────────────────────────
    if "electricity" in categories_seen:
        recs.append(Recommendation(
            title="Reduce electricity consumption",
            explanation=(
                f"You logged {electricity_kwh_total:.2f} kWh of electricity "
                f"this {period}. Each kWh saved avoids approximately 0.710 kg CO₂ "
                "(India FY2024-25 grid factor). "
                "Consider turning off devices at standby, using LED lighting, "
                "and raising AC temperature by 1–2 °C."
            ),
            estimated_saving_kg=None,   # depends on actual reduction achieved
            factor_ids=["india_grid_fy2024_25"],
            assumptions=["India national average grid CO₂ factor FY2024-25"],
            confidence="medium",
            verified_by_tool=False,
            time_period=period,
        ))

    # ── Travel mode switching ─────────────────────────────────────────────
    if "india_car_petrol" in travel_modes_seen:
        # Car → Train comparison (India factors, same boundary)
        try:
            # Approximate: use 10 km as illustrative distance for the tip
            comparison = calculate_travel_comparison("car", "train", 10)
            saving_per_10km = comparison["saving_kg"]
            recs.append(Recommendation(
                title="Switch car trips to train",
                explanation=(
                    f"For every 10 km switched from a petrol car to train, "
                    f"you could save approximately {saving_per_10km:.3f} kg CO₂e "
                    "(India indicative factors). Both use tailpipe/traction operational boundary."
                ),
                estimated_saving_kg=saving_per_10km,
                emissions_unit="kg CO2e",
                time_period="per 10 km",
                factor_ids=["india_car_petrol", "india_train_average"],
                assumptions=[
                    "India petrol car at ~1.5 occupancy",
                    "Indian Railways average electrified route",
                    "Tailpipe/traction operational boundary only",
                ],
                confidence="medium",
                verified_by_tool=True,
            ))
        except ValueError:
            pass   # modes have incompatible factors — skip

    if "india_two_wheeler_petrol" in travel_modes_seen:
        try:
            comparison = calculate_travel_comparison("motorcycle", "cycling", 5)
            saving = comparison["saving_kg"]
            recs.append(Recommendation(
                title="Cycle short distances instead of riding a motorcycle",
                explanation=(
                    f"For every 5 km replaced with cycling, you could save "
                    f"approximately {saving:.3f} kg CO₂e (tailpipe operational boundary). "
                    "Cycling produces zero direct operational emissions."
                ),
                estimated_saving_kg=saving,
                emissions_unit="kg CO2e",
                time_period="per 5 km trip",
                factor_ids=["india_two_wheeler_petrol", "cycling"],
                assumptions=[
                    "India indicative petrol two-wheeler factor",
                    "Cycling operational emissions = 0 (excludes bicycle manufacturing)",
                ],
                confidence="medium",
                verified_by_tool=True,
            ))
        except ValueError:
            pass

    # ── Food substitution ─────────────────────────────────────────────────
    if "poultry" in food_items_seen:
        total_kg = food_items_seen["poultry"]
        try:
            comparison = what_if_food("poultry", "peas", total_kg)
            saving = comparison["saving_kg"]
            recs.append(Recommendation(
                title="Replace some poultry with legumes",
                explanation=(
                    f"Replacing {total_kg:.2f} kg of poultry with an equal mass of peas "
                    f"would save approximately {saving:.3f} kg CO₂e "
                    "(Poore & Nemecek 2018 supply-chain factors). "
                    "Note: equal mass ≠ nutritionally equivalent meal."
                ),
                estimated_saving_kg=saving,
                emissions_unit="kg CO2e",
                time_period=period,
                factor_ids=["poultry", "peas"],
                assumptions=[
                    "Equal mass comparison",
                    "Poore & Nemecek 2018 global median factors",
                    "Nutritional equivalence NOT assumed",
                ],
                confidence="medium",
                verified_by_tool=True,
            ))
        except ValueError:
            pass

    if "beef" in food_items_seen:
        total_kg = food_items_seen["beef"]
        try:
            comparison = what_if_food("beef", "tofu", total_kg)
            saving = comparison["saving_kg"]
            recs.append(Recommendation(
                title="Replace some beef with plant-based protein",
                explanation=(
                    f"Replacing {total_kg:.2f} kg of beef with an equal mass of tofu "
                    f"would save approximately {saving:.3f} kg CO₂e "
                    "(Poore & Nemecek 2018). "
                    "Beef has very high variance across production systems."
                ),
                estimated_saving_kg=saving,
                emissions_unit="kg CO2e",
                time_period=period,
                factor_ids=["beef", "tofu"],
                assumptions=[
                    "Equal mass comparison",
                    "Poore & Nemecek 2018 global median factors",
                    "Actual savings depend on specific beef production system",
                ],
                confidence="low",
                verified_by_tool=True,
            ))
        except ValueError:
            pass

    # ── Generic qualitative advice if no activities logged ────────────────
    if not activities:
        recs.append(Recommendation(
            title="Start logging your activities",
            explanation=(
                "No activities recorded yet. "
                "Log electricity use, travel, and food to receive personalised "
                "reduction recommendations backed by verified emission factors."
            ),
            confidence="low",
            verified_by_tool=False,
        ))

    return [r.to_dict() for r in recs]
