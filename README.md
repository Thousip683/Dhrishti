# Carbon Coach backend — Step 1

Linux setup:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp carbon_coach/.env.example carbon_coach/.env
# Edit carbon_coach/.env with your own Gemini API key
python -m pytest -q
adk web
```

Visit http://localhost:8000 and choose `carbon_coach`.

## Source/Scope
- Electricity: India CEA FY2024-25 weighted average grid generation CO2 (0.710 kg CO2/kWh), reported in Government of India NITI Aayog document.
- Bus: UK DESNZ 2025 average local bus direct GHG 103.85 g CO2e/passenger-km, *not an India factor*.
- Food: Poore & Nemecek 2018 food supply-chain GHG as published by Our World in Data.

Every tool result includes source URL, geography, factor version and accounting boundary. These are selected example factors, not a harmonized global footprint inventory. Future roadmap: India-specific travel, waste factor, API, session persistence, multiple ADK agents, integration, and deployment.
