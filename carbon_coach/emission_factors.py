"""Versioned reference emission factors.

Each factor record MUST carry:
  value        – numeric string (exact, to avoid float-parse drift)
  unit         – measurement unit
  geography    – geographic scope
  version      – source document version / year
  boundary     – accounting boundary description
  source       – citable URL or reference string
  emission_type – "CO2" or "CO2e"

Adding a new factor here automatically makes it available to the engine.
NEVER invent a factor; cite a primary published source.
"""

FACTORS: dict[str, dict[str, dict]] = {
    # ── Electricity ────────────────────────────────────────────────────────
    "electricity": {
        "india_grid_fy2024_25": {
            "value": "0.710",
            "unit": "kg CO2/kWh",
            "emission_type": "CO2",
            "geography": "India",
            "version": "FY2024-25 / CEA v21.0",
            "boundary": (
                "Grid generation, location-based CO2; excludes upstream lifecycle"
            ),
            "source": (
                "https://www.niti.gov.in/sites/default/files/2026-02/"
                "Scenarios-Towards-Viksit-Bharat-and-Net-Zero-Sectoral-Insights-Power.pdf"
            ),
            "notes": (
                "Historical FY2024-25 reference factor. CEA publishes updated values "
                "annually. This factor covers generation only; transmission/distribution "
                "losses are not included."
            ),
        },
    },

    # ── Travel ─────────────────────────────────────────────────────────────
    "travel": {
        "uk_average_local_bus_2025": {
            "value": "0.10385",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "United Kingdom",
            "version": "DESNZ 2025 Table 25",
            "boundary": (
                "Direct operational GHG; excludes fuel upstream lifecycle"
            ),
            "source": (
                "https://assets.publishing.service.gov.uk/media/"
                "6846b0870392ed9b784c0187/2025-GHG-CF-methodology-paper.pdf"
            ),
            "notes": (
                "UK-specific factor. NOT representative of Indian buses. "
                "Do not apply to Indian bus travel without explicit user consent "
                "and clear labelling that it is a foreign reference scenario."
            ),
        },
        "india_two_wheeler_petrol": {
            "value": "0.0889",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "India",
            "version": "IPCC AR5 / TERI 2023 indicative",
            "boundary": "Tailpipe CO2e combustion only; excludes fuel production lifecycle",
            "source": "https://www.teriin.org/",
            "notes": (
                "Indicative India two-wheeler petrol factor. Actual value depends "
                "on vehicle age, load and road condition. Treat as approximate."
            ),
        },
        "india_car_petrol": {
            "value": "0.1693",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "India",
            "version": "CEA/MoRTH 2022 indicative, assumed 1.5 occupancy",
            "boundary": "Tailpipe CO2e combustion only; excludes fuel production lifecycle",
            "source": "https://morth.nic.in/",
            "notes": (
                "Indicative India petrol car factor at ~1.5 average occupancy. "
                "Highly sensitive to vehicle efficiency and occupancy assumptions."
            ),
        },
        "india_train_average": {
            "value": "0.00720",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "India",
            "version": "Indian Railways 2022-23 Energy Report",
            "boundary": "Electrical traction CO2e based on Indian grid mix; excludes infrastructure lifecycle",
            "source": "https://www.indianrailways.gov.in/",
            "notes": (
                "Average across IR network. Electrified routes dominate; diesel "
                "routes have higher per-km emissions. Use as approximate reference only."
            ),
        },
        "walking": {
            "value": "0.0",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "Global",
            "version": "Physical activity — zero operational emissions",
            "boundary": "Operational emissions only; excludes embodied footwear/infrastructure lifecycle",
            "source": "N/A — zero operational fossil fuel combustion",
            "notes": "Walking produces negligible direct emissions. Food calories are not quantified here.",
        },
        "cycling": {
            "value": "0.0",
            "unit": "kg CO2e/passenger-km",
            "emission_type": "CO2e",
            "geography": "Global",
            "version": "Physical activity — zero operational emissions",
            "boundary": "Operational emissions only; excludes bicycle manufacturing lifecycle",
            "source": "N/A — zero operational fossil fuel combustion",
            "notes": "Cycling produces negligible direct emissions. Bicycle manufacturing lifecycle is excluded.",
        },
    },

    # ── Food ───────────────────────────────────────────────────────────────
    "food": {
        "rice": {
            "value": "4.45",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Median value from Poore & Nemecek 2018 meta-analysis. Includes methane from paddies.",
        },
        "poultry": {
            "value": "9.87",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Chicken/poultry median. Actual values vary by production system.",
        },
        "peas": {
            "value": "0.98",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Legumes generally have low footprints due to nitrogen fixation.",
        },
        "wheat": {
            "value": "1.57",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Wheat/flour median from Poore & Nemecek 2018.",
        },
        "beef": {
            "value": "99.48",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Beef median. Very high variance; actual value depends on production system (beef herd vs. dairy herd).",
        },
        "tofu": {
            "value": "3.16",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Tofu/soy-based protein median.",
        },
        "milk": {
            "value": "3.15",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Cow's milk median per kg.",
        },
        "eggs": {
            "value": "4.67",
            "unit": "kg CO2e/kg food",
            "emission_type": "CO2e",
            "geography": "Global study",
            "version": "Poore & Nemecek 2018 / OWID",
            "boundary": "Food production/supply chain footprint",
            "source": "https://ourworldindata.org/grapher/ghg-per-kg-poore",
            "notes": "Eggs median from Poore & Nemecek 2018.",
        },
    },
}


def get_factor(category: str, factor_id: str) -> dict:
    """Return a copy of the factor record; raise ValueError if not found."""
    if category not in FACTORS:
        raise ValueError(f"Unknown category: {category!r}. Available: {list(FACTORS)}")
    cat = FACTORS[category]
    if factor_id not in cat:
        raise ValueError(
            f"Unknown factor {factor_id!r} in category {category!r}. "
            f"Available: {list(cat)}"
        )
    return dict(cat[factor_id])


def list_factors(category: str | None = None) -> dict:
    """Return a lightweight summary of available factors, optionally filtered."""
    result: dict[str, dict] = {}
    cats = {category: FACTORS[category]} if category and category in FACTORS else FACTORS
    for cat_name, entries in cats.items():
        result[cat_name] = {
            fid: {
                "unit": f["unit"],
                "geography": f["geography"],
                "version": f["version"],
                "emission_type": f.get("emission_type", "unknown"),
            }
            for fid, f in entries.items()
        }
    return result
