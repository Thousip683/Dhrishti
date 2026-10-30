"""Carbon Coach — local CLI demonstration.

Run from the carbon-coach-backend/ directory (inside the activated venv):

    python scripts/demo_agent.py

Requires GOOGLE_API_KEY to be set in carbon_coach/.env
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

# Ensure carbon_coach is importable when run as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from carbon_coach.reference_agent.service import CarbonCoachService


BANNER = """
╔══════════════════════════════════════════════════════════╗
║         Carbon Coach — Local CLI Demo (DevFest 2026)    ║
╠══════════════════════════════════════════════════════════╣
║  Commands:  type a message and press Enter               ║
║  Prefixes:  [te] for Telugu   [hi] for Hindi             ║
║  Special:   summary | activities | quit                  ║
╚══════════════════════════════════════════════════════════╝
"""

DEMO_SCRIPT = [
    ("en", "I used 5 kWh of electricity today. Please log it."),
    ("en", "How much electricity-related CO2 have I logged this week?"),
    ("en", "Compare the production emissions of 200g of poultry and 200g of peas."),
    ("en", "What if I switch from driving my car to taking the train for 15 km?"),
    ("te", "ఈరోజు నేను 5 kWh విద్యుత్ వినియోగించాను."),
    ("hi", "आज मैंने 5 kWh बिजली इस्तेमाल की।"),
]


async def run_demo(service: CarbonCoachService, session_id: str, user_id: str):
    print("\n🤖 Running scripted demonstration...\n")
    for lang, msg in DEMO_SCRIPT:
        lang_label = {"en": "🇬🇧 English", "te": "🇮🇳 Telugu", "hi": "🇮🇳 Hindi"}.get(lang, lang)
        print(f"\n{'─'*60}")
        print(f"{lang_label} ▶ {msg}")
        print("─" * 60)
        result = await service.chat(msg, session_id, user_id, language=lang)
        print(f"🤖 {result['reply']}")
        if result["tool_calls_made"]:
            print(f"   [Tools called: {', '.join(result['tool_calls_made'])}]")


async def interactive_chat(service: CarbonCoachService, session_id: str, user_id: str):
    print(BANNER)
    print(f"Session ID: {session_id}")
    print("Type 'demo' to run the scripted demonstration, or start chatting.\n")

    while True:
        try:
            raw = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not raw:
            continue

        if raw.lower() == "quit":
            print("Goodbye!")
            break

        if raw.lower() == "demo":
            await run_demo(service, session_id, user_id)
            continue

        if raw.lower() == "summary":
            summary = service.get_summary(user_id, "week", session_id)
            print(f"\n📊 Week summary: {summary}\n")
            continue

        if raw.lower() == "activities":
            acts = service.get_activities(user_id, session_id, "week")
            print(f"\n📋 Activities ({len(acts)}):")
            for a in acts:
                c = a["calculation"]
                print(f"  • {c['category']} / {c['factor_id']}: {c['emissions_kg']:.4f} {c['emissions_unit']}")
            print()
            continue

        # Detect language prefix
        lang = "en"
        msg = raw
        if raw.startswith("[te]"):
            lang, msg = "te", raw[4:].strip()
        elif raw.startswith("[hi]"):
            lang, msg = "hi", raw[4:].strip()

        try:
            result = await service.chat(msg, session_id, user_id, language=lang)
            print(f"\n🤖 {result['reply']}\n")
            if result["tool_calls_made"]:
                print(f"   [Tools: {', '.join(result['tool_calls_made'])}]\n")
        except Exception as exc:
            print(f"\n❌ Error: {exc}\n")


async def main():
    # Check for API key
    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key or key == "PASTE_YOUR_KEY_HERE":
        print("❌ GOOGLE_API_KEY not set. Edit carbon_coach/.env and try again.")
        sys.exit(1)

    session_id = str(uuid.uuid4())
    user_id = "demo_user"

    service = CarbonCoachService()
    await service.start()

    try:
        await interactive_chat(service, session_id, user_id)
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
