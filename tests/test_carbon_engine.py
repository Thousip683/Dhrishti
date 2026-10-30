import pytest
from carbon_coach.carbon_engine import (
    calculate, calculate_electricity_emissions,
    calculate_travel_emissions, calculate_food_emissions,
    calculate_reduction,
)


def test_electricity():
    result = calculate_electricity_emissions(5)
    assert result["emissions_kg"] == pytest.approx(3.55)
    assert result["emissions_unit"] == "kg CO2"
    assert result["geography"] == "India"
    assert result["source"].startswith("https://")


def test_uk_bus():
    result = calculate_travel_emissions("uk_bus", 12)
    assert result["emissions_kg"] == pytest.approx(1.2462)
    assert result["geography"] == "United Kingdom"


@pytest.mark.parametrize("food,quantity,expected", [
    ("rice", 0.2, 0.89),
    ("poultry", 0.1, 0.987),
    ("peas", 0.25, 0.245),
])
def test_food(food, quantity, expected):
    assert calculate_food_emissions(food, quantity)["emissions_kg"] == pytest.approx(expected)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), "abc", True])
def test_invalid_quantity(value):
    with pytest.raises(ValueError):
        calculate_electricity_emissions(value)


def test_missing_factor():
    # Generic 'bus' (Indian bus) has no verified factor; should raise ValueError
    with pytest.raises(ValueError):
        calculate_travel_emissions("bus", 10)


def test_no_fabricated_meal_factor():
    with pytest.raises(ValueError):
        calculate_food_emissions("vegetarian_lunch", 1)


def test_comparison_same_units():
    result = calculate_reduction("food", "poultry", "peas", 0.2)
    assert result["saving_kg"] == pytest.approx(1.778)


def test_wrong_category_or_factor():
    with pytest.raises(ValueError):
        calculate("waste", "unknown", 10)
