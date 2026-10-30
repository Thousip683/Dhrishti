# Step 2 — Multi-agent Carbon Coach + SQLite session storage

## From the project root (Linux)

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
cp carbon_coach/.env.example carbon_coach/.env  # only if you have not already configured it
# Edit carbon_coach/.env with your Gemini API key. Do not share or commit it.
python -m pytest -v
adk web
```

Select `carbon_coach`. Prompts:
- `I used 5 kWh of electricity. Please log it.`
- `How much electricity-related CO2 have I logged this week?`
- `Compare the production emissions of 200 g poultry and 200 g peas.`

The root ADK agent transfers requests to specialist agents. Each logging tool uses the ADK ToolContext session ID, and SQLite saves records separately per session. SQLite lives in `carbon_activities.sqlite3` by default, or set `CARBON_DB_PATH` (absolute path). ADK web session state is not the same as SQLite storage. If you start a new ADK session, activity history is intentionally separate.

Only the configured factors are supported: India electricity, UK bus reference, and three food types. UK bus factor is **not** representative of India, and no Indian bus factor is configured. Ask permission before applying a foreign factor. Units and accounting boundaries are shown and segregated in summary totals. `week` means rolling seven days UTC; `today` means UTC today. Food mass in kg; electricity in kWh. No inference from appliance usage hours. A food mass comparison is not a nutritionally equivalent substitution.

This is local development persistence only. For Cloud Run use a managed database, authenticated user IDs and persistent ADK session service. `/api` frontend endpoints and deployment are reserved for Step 3.
