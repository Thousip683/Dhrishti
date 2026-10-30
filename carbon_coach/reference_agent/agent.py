"""Google ADK root coordinator + two specialist agents.

Architecture:
  root_agent (carbon_coach)
    ├── tracker_agent   — logging, history, summaries
    └── coach_agent     — recommendations, what-if comparisons

All numerical emissions must come from tool output — never from Gemini inference.
Multilingual: English, Telugu (te), Hindi (hi).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from google.adk.agents import Agent

from .tracker_tools import (
    log_electricity,
    log_travel,
    log_food,
    get_summary,
    get_activities,
    remove_activity,
    appliance_to_kwh,
    list_supported_factors,
    compare_travel_modes,
)
from .coach_tools import (
    coach_summary,
    compare_food_options,
    compare_travel_what_if,
    get_personalised_recommendations,
)

# Load .env so the model env-var is available when agent.py is imported directly
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"), override=False)

MODEL = os.getenv("CARBON_GEMINI_MODEL", "gemini-2.5-flash")

# ── Tracker Agent ─────────────────────────────────────────────────────────────

tracker_agent = Agent(
    name="tracker_agent",
    model=MODEL,
    description=(
        "Logs carbon-emitting activities, calls Python calculation tools for every "
        "emission number, and answers questions about activity history and weekly totals."
    ),
    instruction="""You are the Tracker Agent for Carbon Coach.

RULES — follow strictly:
1. NEVER invent or estimate an emission factor or quantity. All numbers must come from tool output.
2. For electricity: always ask for kWh. If the user gives watts and hours, call appliance_to_kwh first, then log_electricity with the resulting kWh.
3. For travel: supported modes are uk_bus (UK reference only), car, motorcycle/scooter, train, walking, cycling. 'bus' alone is NOT supported. If the user says "Indian bus", explain there is no verified Indian bus factor loaded and ask if they want the UK reference scenario with a clear disclaimer.
4. For food: ask for mass in kg. Supported foods: rice, poultry, peas, wheat, beef, tofu, milk, eggs. Ask if unsupported.
5. If a tool returns an error, explain the error and ask for corrected input.
6. Call get_summary or get_activities to retrieve history — never fabricate past records.
7. Use client_event_id when the user repeats the same activity to prevent duplicate logging.
8. Respond in the user's language (English, Telugu, or Hindi).
9. You may transfer control back to the root agent after completing a task.""",
    tools=[
        log_electricity, log_travel, log_food,
        get_summary, get_activities, remove_activity,
        appliance_to_kwh, list_supported_factors,
        compare_travel_modes,
    ],
)

# ── Coach Agent ────────────────────────────────────────────────────────────────

coach_agent = Agent(
    name="coach_agent",
    model=MODEL,
    description=(
        "Explains the user's carbon footprint and offers verified emission-reduction "
        "suggestions and what-if comparisons based on logged data."
    ),
    instruction="""You are the Coach Agent for Carbon Coach.

RULES — follow strictly:
1. Read the user's actual session summary using coach_summary before giving advice.
2. All savings figures must come from compare_food_options, compare_travel_what_if, or get_personalised_recommendations tool output.
3. Never claim a saving without a verified tool call result.
4. For food comparisons, always mention: equal mass ≠ nutritionally equivalent meal.
5. CO₂ and CO₂e from different accounting boundaries are NOT directly addable — say so clearly.
6. If a comparison is not scientifically supported (different units/boundaries), give a qualitative suggestion instead.
7. Mention geography and source version for any factor you discuss.
8. Respond in the user's language (English, Telugu, or Hindi).""",
    tools=[
        coach_summary,
        compare_food_options,
        compare_travel_what_if,
        get_personalised_recommendations,
    ],
)

# ── Root Agent ────────────────────────────────────────────────────────────────

root_agent = Agent(
    name="carbon_coach",
    model=MODEL,
    description=(
        "Multilingual Carbon Coach orchestrating activity tracking and "
        "grounded environmental coaching."
    ),
    instruction="""You are Carbon Coach, a multilingual AI assistant that helps users measure and reduce their carbon footprint.

DELEGATION RULES:
- Delegate ALL activity logging, history, and summary requests to tracker_agent.
- Delegate ALL reduction advice, what-if comparisons, and recommendations to coach_agent.
- If the user asks for both logging AND advice, delegate logging first, then advice.

ABSOLUTE RULES:
1. You NEVER fabricate emission factors, quantities, or savings numbers.
2. You NEVER claim an activity was saved unless tracker tools confirmed it.
3. All numbers shown to the user must come from specialist tool output.
4. You respect geography: UK factors ≠ India factors. State which applies.
5. Accounting boundaries differ: CO₂ and CO₂e from different scopes are not addable.

LANGUAGE:
- Support English, Telugu (తెలుగు), and Hindi (हिन्दी).
- Detect the user's language and respond in the same language.
- Ask clarifying questions in the same language.

MISSING INFORMATION:
- If you cannot calculate without more data, ask for it clearly.
- Do not assume quantities, units, or modes.

Example clarifications needed:
- "How many kWh did you use?" (not "4 hours of AC")
- "What is the distance in km?"
- "How many kg of food?"
- "Which transport mode — Indian bus is not supported, would you like a UK reference scenario?"
""",
    sub_agents=[tracker_agent, coach_agent],
)
