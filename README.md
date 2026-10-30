# Dhrishti Carbon Coach

A Google ADK coordinator with Tracker and Coach specialists using Gemini to select deterministic Python tools for travel, electricity, food and waste estimates. Every calculation includes factor evidence. Activity logs, date-filtered summaries and personalized reduction scenarios share one calculation engine.

## Current implementation

- Native Gemini function calling through Google ADK.
- Eleven verified factors extracted from published UK DESNZ 2025 and Poore and Nemecek food data.
- Decimal arithmetic, explicit car occupancy, appliance energy conversion and defined food recipes.
- Session activity memory, totals, daily buckets, hypothetical savings and record deletion.
- FastAPI session credentials, idempotent calculations and writes, corrections and generated OpenAPI.
- Final replies assembled from tool receipts, preventing model-generated numerical claims.
- Automated arithmetic, REST and scripted ADK runner tests.

The API defaults to durable SQLite storage and also supports PostgreSQL. API sessions and the ADK development UI remain separate. Neither is a public production deployment; rate limits and deployment hardening are still planned. Bind local services to localhost. Explicit memory mode loses history on restart.

## Setup on Windows

From this directory, with Python 3.12 and uv installed:

```powershell
uv sync --frozen
# Copy only when .env does not already exist.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run alembic upgrade head
```

Set your own `GOOGLE_API_KEY` in `.env`. The model defaults to the ADK quickstart alias `gemini-flash-latest`; set `GEMINI_MODEL` to an available stable model ID for a pinned deployment. No key is needed for direct API calculations or tests. Never commit `.env`.

## Run the application frontend

The built frontend and API share http://127.0.0.1:8001. To build from source, install Node.js 22.12 or newer and pnpm 11.25.0, then run:

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run alembic upgrade head
uv run uvicorn carbon_coach.api:app --host 127.0.0.1 --port 8001
```

For frontend development, run `pnpm dev` in `frontend` while the API runs on port 8001. Open the printed port 5173 URL; Vite proxies API requests to preserve the browser origin. Configure `ALLOWED_ORIGINS` explicitly if changing ports. Never put the provider key in a `VITE_` environment variable.

The application supports browser-session setup and restoration, responsive navigation, source disclosure, overview statistics, integrated chat and settings with erasure. Manual forms now support all four categories, source-backed previews and explicit saving. Appliance conversion evidence, session-scoped drafts and retry-safe recovery are included. See `docs/Stage_3_Activity_Logging.md`. HttpOnly cookies protect browser credentials; mutations also require an origin check and CSRF token. Browser endpoints and retry semantics are documented in `docs/Stage_2_Browser_API.md`.

Frontend checks: `pnpm test`, `pnpm build` and `pnpm test:e2e`. Browser tests use installed Chrome, start a disposable mock-backed API on port 8012, and stop that test server afterward. They never call the provider.

## Integrated agent and chat

Open http://127.0.0.1:8001/chat to use the imported Dhrishti multi-agent architecture with the application ledger. Tracker and Coach share the same saved activities as manual entry. Chat history survives application storage reloads and request keys prevent replaying acknowledged turns. Core receipts support English, Hindi and Telugu; detailed source explanations can remain in English.

The original repository implementation and tests are preserved in `carbon_coach/reference_agent` and `tests/reference_agent`. Its standalone ledger and unreviewed or CO2-only factors are not wired into live CO2e totals. See `docs/AGENT_INTEGRATION.md` for source commit, compatibility decisions and configuration.

## Run the separate development interface

```powershell
uv run adk web --host 127.0.0.1 --port 8000 --session_service_uri memory:// carbon_coach
```

Open http://127.0.0.1:8000 and choose Carbon Coach if prompted. Example prompts:

- “I travelled 12 km by bus today.”
- “I used the AC for 4 hours.” This should ask for energy or average electrical power and grid region.
- “What are my logged emissions this week?”
- “Suggest reductions for the activities I logged.”

UK factors are reference estimates, not India factors. Electricity requires explicit UK region. An India electricity factor has not been configured. Food recipes use 0.1 kg raw rice and 0.15 kg peas or poultry per serving; cooking, oil and seasonings are excluded. The agent must ask whether the recipe matches the user's meal.

## Run the API

Apply migrations first. Default SQLite stores application records in the ignored `carbon_coach.db` file. Set `DATABASE_URL` for PostgreSQL or `STORAGE_MODE=memory` for disposable development. See `docs/Database_Runbook.md`.

```powershell
uv run uvicorn carbon_coach.api:app --host 127.0.0.1 --port 8001
```

Open http://127.0.0.1:8001/docs for interactive API documentation or `/openapi.json` for the generated schema. Create a session, copy its token, then send `Authorization: Bearer <token>` and a unique `Idempotency-Key` with each calculation or mutation. The interactive docs expose Authorization as a header parameter on protected routes.

### PowerShell example without Gemini

```powershell
$base = 'http://127.0.0.1:8001/api/v1'
$session = Invoke-RestMethod -Method Post -Uri "$base/sessions" -ContentType 'application/json' -Body '{}'
$headers = @{ Authorization = "Bearer $($session.session_token)"; 'Idempotency-Key' = [guid]::NewGuid().ToString() }
$calc = Invoke-RestMethod -Method Post -Uri "$base/sessions/$($session.session_id)/calculations" -Headers $headers -ContentType 'application/json' -Body '{"category":"travel","input":{"mode":"bus","distance_km":"12"}}'
$calc.calculation
$headers['Idempotency-Key'] = [guid]::NewGuid().ToString()
$body = @{ calculation_id = $calc.calculation.id; activity_date = (Get-Date -Format 'yyyy-MM-dd') } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "$base/sessions/$($session.session_id)/activities" -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod -Uri "$base/sessions/$($session.session_id)/summary?period=today" -Headers $headers
```

## Verification

```powershell
uv run pytest -q
```

Tests use published-factor arithmetic and a scripted model to run the real ADK tool loop. They do not claim to validate live Gemini behavior or quota. A live test requires the configured key and provider access.

## Provenance

`carbon_coach/data/factors.json` contains exact source IDs, rows, values and unit conversions. Original source snapshots are retained. `scripts/import_factors.py` rebuilds the registry offline and requires openpyxl in the author's import environment; normal application startup needs no spreadsheet library or network.

- UK DESNZ 2025 flat dataset: https://www.gov.uk/government/publications/greenhouse-gas-reporting-conversion-factors-2025
- Food data: https://ourworldindata.org/grapher/ghg-per-kg-poore — Poore and Nemecek (2018), processed by Our World in Data.

Historical 2025 UK factors are intentionally versioned; they are not represented as the latest 2026 release. UK generation-only electricity excludes transmission and distribution and upstream fuel stages. Travel uses operational factors. Waste covers treatment only. Food uses global supply-chain averages. The combined logged estimate is not a complete lifecycle inventory. Research data remains subject to its original provider's terms; the UK source is covered by its published government licensing terms.

## Remaining PRD and API work

The specification documents describe the target product; this first implementation covers a subset. Stages 0 through 3 are complete: typed contracts, frontend shell, protected browser sessions, gateway boundary and durable transactional storage. Outstanding work includes raw bearer-creation idempotency, full period dashboards, paginated lists, comparison periods, streaming or resumable requests, remaining target-contract extensions, locale support, rate limits, structured pending activity resolution, the remaining frontend workflows and cloud deployment. See `docs/Implementation_Status.md`. API chat currently has a 60-second bounded run and returns a stored partial-failure receipt rather than the target 202 polling protocol.

API corrections work; conversational correction tooling is still pending. The live agent's decisions about logging intent and missing-input questions still need provider-backed golden evaluations. Deterministic upstream tests are included; live tests are excluded by default and require an explicit `-m integration` run. Full session erasure is available through the API. Local credentials and receipts must not be used for sensitive information.

Product specifications are in `docs/Carbon_Coach_PRD.md`, `docs/Carbon_Coach_API_Contract.md` and `docs/Carbon_Coach_Tech_Stack.md`.

## Contract artifacts

Run `uv run python scripts/export_contract.py` to regenerate OpenAPI, frontend TypeScript definitions and deterministic UI fixtures; add `--check` to detect drift. The screen map and contract gap checklist are in `docs/Stage_0_Contract_and_Screen_Map.md`. The frontend shell and category forms are implemented; the full dashboard begins in Stage 4.
