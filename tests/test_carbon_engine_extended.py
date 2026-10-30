"""Extended carbon engine tests — deterministic, no Gemini required.

Covers:
  - All new travel modes (car, motorcycle, train, walking, cycling)
  - Appliance kWh conversion
  - Boundary-compatible and incompatible comparisons
  - All new food factors
  - Unsupported modes / categories
  - Factor metadata completeness
"""
import math
import pytest
from carbon_coach.carbon_engine import (
    calculate,
    calculate_electricity_emissions,
    calculate_travel_emissions,
    calculate_food_emissions,
    calculate_appliance_kwh,
    calculate_reduction,
    calculate_travel_comparison,
)
from carbon_coach.emission_factors import list_factors, get_factor


# ── Electricity ────────────────────────────────────────────────────────────────

class TestElectricity:
    def test_5kwh_india(self):
        r = calculate_electricity_emissions(5)
        assert r["emissions_kg"] == pytest.approx(3.55)
        assert r["emissions_unit"] == "kg CO2"
        assert r["geography"] == "India"
        assert r["source"].startswith("https://")
        assert "version" in r
        assert "boundary" in r

    def test_zero_kwh(self):
        r = calculate_electricity_emissions(0)
        assert r["emissions_kg"] == 0.0

    def test_fractional_kwh(self):
        r = calculate_electricity_emissions(2.5)
        assert r["emissions_kg"] == pytest.approx(1.775)

    def test_factor_metadata_complete(self):
        f = get_factor("electricity", "india_grid_fy2024_25")
        for key in ("value", "unit", "emission_type", "geography", "version", "boundary", "source"):
            assert key in f, f"Missing key: {key}"


# ── Appliance kWh conversion ──────────────────────────────────────────────────

class TestApplianceKwh:
    def test_1500w_2h(self):
        r = calculate_appliance_kwh(1500, 2)
        assert r["kwh"] == pytest.approx(3.0)
        assert "formula" in r

    def test_100w_8h(self):
        r = calculate_appliance_kwh(100, 8)
        assert r["kwh"] == pytest.approx(0.8)

    def test_zero_watts(self):
        r = calculate_appliance_kwh(0, 4)
        assert r["kwh"] == 0.0

    def test_hours_over_24_raises(self):
        with pytest.raises(ValueError):
            calculate_appliance_kwh(1000, 25)

    def test_negative_watts_raises(self):
        with pytest.raises(ValueError):
            calculate_appliance_kwh(-100, 2)

    def test_does_not_calculate_emissions(self):
        r = calculate_appliance_kwh(1500, 2)
        # Should NOT contain emissions_kg — the caller must call log_electricity next
        assert "emissions_kg" not in r


# ── Travel ─────────────────────────────────────────────────────────────────────

class TestTravel:
    def test_uk_bus_alias(self):
        r = calculate_travel_emissions("uk_bus", 12)
        assert r["emissions_kg"] == pytest.approx(1.2462)
        assert r["geography"] == "United Kingdom"

    def test_uk_bus_alias_full_name(self):
        r = calculate_travel_emissions("uk_average_local_bus", 10)
        assert r["emissions_kg"] > 0

    def test_car_india(self):
        r = calculate_travel_emissions("car", 10)
        assert r["emissions_kg"] == pytest.approx(10 * 0.1693)
        assert "India" in r["geography"]

    def test_motorcycle_alias(self):
        r = calculate_travel_emissions("motorcycle", 5)
        assert r["emissions_kg"] > 0

    def test_scooter_alias(self):
        r = calculate_travel_emissions("scooter", 5)
        r2 = calculate_travel_emissions("motorcycle", 5)
        assert r["emissions_kg"] == pytest.approx(r2["emissions_kg"])

    def test_train_india(self):
        r = calculate_travel_emissions("train", 100)
        assert r["emissions_kg"] == pytest.approx(100 * 0.00720)
        assert "India" in r["geography"]

    def test_walking_zero_emissions(self):
        r = calculate_travel_emissions("walking", 5)
        assert r["emissions_kg"] == 0.0

    def test_cycling_zero_emissions(self):
        r = calculate_travel_emissions("cycling", 10)
        assert r["emissions_kg"] == 0.0

    def test_cycling_alias(self):
        r1 = calculate_travel_emissions("cycle", 10)
        r2 = calculate_travel_emissions("bicycle", 10)
        assert r1["emissions_kg"] == r2["emissions_kg"]

    # Unsupported modes
    def test_bus_generic_unsupported(self):
        with pytest.raises(ValueError, match="No verified emission factor"):
            calculate_travel_emissions("bus", 10)

    def test_indian_bus_unsupported(self):
        with pytest.raises(ValueError):
            calculate_travel_emissions("indian_bus", 10)

    def test_flight_unsupported(self):
        with pytest.raises(ValueError):
            calculate_travel_emissions("flight", 500)

    def test_auto_rickshaw_unsupported(self):
        with pytest.raises(ValueError):
            calculate_travel_emissions("autorickshaw", 3)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            calculate_travel_emissions("hoverboard", 5)


# ── Food ───────────────────────────────────────────────────────────────────────

class TestFood:
    @pytest.mark.parametrize("food,kg,expected", [
        ("rice", 0.2, 0.89),
        ("poultry", 0.1, 0.987),
        ("peas", 0.25, 0.245),
        ("wheat", 1.0, 1.57),
        ("beef", 0.5, 49.74),
        ("tofu", 1.0, 3.16),
        ("milk", 1.0, 3.15),
        ("eggs", 1.0, 4.67),
    ])
    def test_food_emissions(self, food, kg, expected):
        r = calculate_food_emissions(food, kg)
        assert r["emissions_kg"] == pytest.approx(expected, rel=1e-3)
        assert r["emissions_unit"] == "kg CO2e"

    def test_case_insensitive(self):
        r1 = calculate_food_emissions("Rice", 1)
        r2 = calculate_food_emissions("rice", 1)
        assert r1["emissions_kg"] == r2["emissions_kg"]

    def test_unsupported_food_raises(self):
        with pytest.raises(ValueError):
            calculate_food_emissions("vegetarian_lunch", 1)

    def test_unsupported_food_curry_raises(self):
        with pytest.raises(ValueError):
            calculate_food_emissions("chicken_curry", 0.3)


# ── Travel comparison ──────────────────────────────────────────────────────────

class TestTravelComparison:
    def test_car_vs_train(self):
        r = calculate_travel_comparison("car", "train", 10)
        assert r["saving_kg"] > 0   # train lower emission
        assert "original" in r
        assert "alternative" in r

    def test_car_vs_walking(self):
        r = calculate_travel_comparison("car", "walking", 5)
        assert r["saving_kg"] == pytest.approx(5 * 0.1693)

    def test_walking_vs_cycling_same(self):
        r = calculate_travel_comparison("walking", "cycling", 10)
        assert r["saving_kg"] == pytest.approx(0.0)

    def test_incompatible_categories_raise(self):
        # Comparing electricity factor against travel factor — different units
        with pytest.raises(ValueError):
            calculate_reduction(
                "electricity", "india_grid_fy2024_25",
                "uk_average_local_bus_2025",
                1,
            )


# ── Reduction calculation ──────────────────────────────────────────────────────

class TestReduction:
    def test_food_saving_poultry_vs_peas(self):
        r = calculate_reduction("food", "poultry", "peas", 0.2)
        assert r["saving_kg"] == pytest.approx(1.778)
        assert r["saving_kg"] > 0

    def test_beef_vs_tofu(self):
        r = calculate_reduction("food", "beef", "tofu", 1.0)
        assert r["saving_kg"] > 0
        assert r["saving_kg"] == pytest.approx(99.48 - 3.16)

    def test_incompatible_categories_raise(self):
        with pytest.raises(ValueError):
            calculate_reduction("electricity", "india_grid_fy2024_25", "uk_average_local_bus_2025", 1)


# ── Factor registry ────────────────────────────────────────────────────────────

class TestFactorRegistry:
    def test_list_all_factors(self):
        factors = list_factors()
        assert "electricity" in factors
        assert "travel" in factors
        assert "food" in factors

    def test_list_travel_factors(self):
        factors = list_factors("travel")
        assert "uk_average_local_bus_2025" in factors["travel"]
        assert "india_car_petrol" in factors["travel"]
        assert "india_train_average" in factors["travel"]
        assert "walking" in factors["travel"]
        assert "cycling" in factors["travel"]

    def test_list_food_factors(self):
        factors = list_factors("food")
        food_ids = factors["food"]
        for expected in ["rice", "poultry", "peas", "wheat", "beef", "tofu", "milk", "eggs"]:
            assert expected in food_ids

    def test_get_factor_returns_copy(self):
        f1 = get_factor("food", "rice")
        f1["value"] = "99"
        f2 = get_factor("food", "rice")
        assert f2["value"] == "4.45"  # original not mutated

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError):
            get_factor("waste", "landfill")

    def test_unknown_factor_id_raises(self):
        with pytest.raises(ValueError):
            get_factor("food", "mystery_meat")
