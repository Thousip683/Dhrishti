# Carbon Coach Agent — Integration Guide for FastAPI Developer

> **This document is the handoff from the AI agent module to the FastAPI backend developer.**

---

## Table of Contents

1. [Installation](#1-installation)
2. [Configuration](#2-configuration)
3. [Initialising CarbonCoachService](#3-initialising-carboncoacservice)
4. [FastAPI Lifespan Pattern](#4-fastapi-lifespan-pattern)
5. [Calling chat()](#5-calling-chat)
6. [Passing Authenticated Identity](#6-passing-authenticated-identity)
7. [Session IDs](#7-session-ids)
8. [Activity History](#8-activity-history)
9. [Emission Summaries](#9-emission-summaries)
10. [Recommendations](#10-recommendations)
11. [Campus Analytics](#11-campus-analytics)
12. [Input / Output Structures](#12-input--output-structures)
13. [Error Handling](#13-error-handling)
14. [Concurrency Safety](#14-concurrency-safety)
15. [Storage Configuration](#15-storage-configuration)
16. [Running Tests](#16-running-tests)
17. [Known Limitations](#17-known-limitations)
18. [Google Cloud Permissions](#18-google-cloud-permissions)

---

## 1. Installation

```bash
cd carbon-coach-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**`requirements.txt`** (minimal):
```
google-adk>=2.13.0
google-genai>=2.34.0
python-dotenv>=1.2.4
pydantic>=2.0
```

---

## 2. Configuration

Copy the example env file and set your key:

```bash
cp carbon_coach/.env.example carbon_coach/.env
# Edit carbon_coach/.env:
#   GOOGLE_API_KEY=your_real_key_here
#   GOOGLE_GENAI_USE_VERTEXAI=FALSE
```

All configuration is read from **environment variables** at import time.

| Variable | Default | Description |
|---|---|---|
| `GOOGLE_API_KEY` | — | Required. Your Gemini API key. |
| `GOOGLE_GENAI_USE_VERTEXAI` | `FALSE` | Set `TRUE` for Vertex AI. |
| `CARBON_GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name. |
| `CARBON_DB_PATH` | `carbon_activities.sqlite3` | SQLite file path. |
| `CAMPUS_MIN_GROUP_SIZE` | `3` | Privacy threshold for campus aggregates. |
| `CARBON_LOG_LEVEL` | `INFO` | Python logging level. |

> **Cloud Run**: Set `CARBON_DB_PATH` to a path on a mounted persistent volume, or switch to a managed database by providing a custom `session_service`.

---

## 3. Initialising CarbonCoachService

```python
from carbon_coach.service import CarbonCoachService

# Development (InMemory sessions — lost on restart)
service = CarbonCoachService()

# With custom model
service = CarbonCoachService(model="gemini-2.5-flash")

# With dependency-injected session service (production)
from google.adk.sessions import InMemorySessionService  # or your custom one
service = CarbonCoachService(session_service=my_session_service)
```

---

## 4. FastAPI Lifespan Pattern

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from carbon_coach.service import CarbonCoachService

@asynccontextmanager
async def lifespan(app: FastAPI):
    service = CarbonCoachService()
    await service.start()
    app.state.carbon_service = service
    yield
    await service.stop()

app = FastAPI(lifespan=lifespan)

# In a route:
@app.post("/chat")
async def chat(request: ChatRequest, req: Request):
    service: CarbonCoachService = req.app.state.carbon_service
    # user_id MUST come from your verified auth middleware, not from request body
    user_id = req.state.authenticated_user_id
    result = await service.chat(
        message=request.message,
        session_id=request.session_id,
        user_id=user_id,
        language=request.language,
    )
    return result
```

---

## 5. Calling chat()

```python
result = await service.chat(
    message="I used 5 kWh of electricity today. Log it.",
    session_id="sess_abc123",    # caller-managed, persisted across turns
    user_id="alice@example.com", # pre-authenticated by FastAPI auth
    language="en",               # "en" | "te" | "hi"
)
# result = {
#   "session_id": "sess_abc123",
#   "user_id": "alice@example.com",
#   "reply": "I've logged 5 kWh using the India grid factor...",
#   "tool_calls_made": ["log_electricity"],
#   "raw_events": [...]   # ADK events (for debugging)
# }
```

**Synchronous wrapper** (non-async callers):
```python
result = service.chat_sync(message, session_id, user_id, language)
```

---

## 6. Passing Authenticated Identity

> ⚠️ **Critical security note**: The `user_id` parameter in `chat()` and all other methods **must** be set by your authentication middleware — never from an untrusted request body.

```python
# FastAPI dependency for authenticated user
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    # validate token, extract user_id
    return verified_user_id   # pass this as user_id to service methods
```

The AI module never validates identity — it trusts whatever `user_id` is passed.

---

## 7. Session IDs

- Generate a `session_id` (e.g. UUID4) when a new conversation starts.
- Persist it in your frontend/database and reuse it across turns.
- Each new `session_id` starts a fresh ADK conversation context.
- The SQLite activity ledger stores records per `session_id`.

```python
import uuid
session_id = str(uuid.uuid4())  # create once per conversation
```

---

## 8. Activity History

```python
# By session (for current conversation):
activities = service.get_activities(
    user_id="alice@example.com",
    session_id="sess_abc123",
    period="week",   # "today" | "week" | "month" | "all"
)

# Across all sessions for a user:
activities = service.get_activities(
    user_id="alice@example.com",
    period="week",
)

# Each activity:
# {
#   "activity_id": "uuid",
#   "created_at": "2026-10-30T10:00:00+00:00",
#   "calculation": {
#       "category": "electricity",
#       "factor_id": "india_grid_fy2024_25",
#       "quantity": 5.0,
#       "emissions_kg": 3.55,
#       "emissions_unit": "kg CO2",
#       "geography": "India",
#       "version": "FY2024-25 / CEA v21.0",
#       "boundary": "Grid generation...",
#       "source": "https://..."
#   }
# }
```

---

## 9. Emission Summaries

```python
summary = service.get_summary(
    user_id="alice@example.com",
    period="week",
    session_id="sess_abc123",  # optional; cross-session if omitted
)
# {
#   "period": "week",
#   "activity_count": 3,
#   "totals": [
#       {"emissions_unit": "kg CO2",  "boundary": "...", "emissions_kg": 3.55},
#       {"emissions_unit": "kg CO2e", "boundary": "...", "emissions_kg": 1.23},
#   ],
#   "note": "Totals are separated by gas type and accounting boundary..."
# }
```

> ⚠️ `kg CO2` and `kg CO2e` totals are **not addable**. Present them separately.

---

## 10. Recommendations

```python
recs = service.get_recommendations(
    user_id="alice@example.com",
    session_id="sess_abc123",  # optional
    period="week",
)
# Each recommendation:
# {
#   "title": "Switch car trips to train",
#   "explanation": "For every 10 km switched...",
#   "estimated_saving_kg": 1.621,
#   "emissions_unit": "kg CO2e",
#   "time_period": "per 10 km",
#   "factor_ids": ["india_car_petrol", "india_train_average"],
#   "assumptions": ["India petrol car at ~1.5 occupancy", ...],
#   "confidence": "medium",
#   "verified_by_tool": true
# }
```

---

## 11. Campus Analytics

```python
# Campus-level summary
summary = service.get_campus_summary(
    campus_id="IIT_Hyderabad",
    period="week",
)

# Department comparison
depts = service.get_department_comparison(
    campus_id="IIT_Hyderabad",
    departments=["CSE", "ECE", "Mechanical"],
    period="week",
)

# Hostel leaderboard
leaderboard = service.get_campus_leaderboard(
    campus_id="IIT_Hyderabad",
    hostels=["NH1", "NH2", "GH"],
    period="week",
)
```

**To opt users in to campus analytics**, your FastAPI layer must:
1. Ask for explicit user consent.
2. Pass `campus_group` and `campus_opted_in=True` to `add_activity()` in `activity_tracker.py`.
3. Use a group label like `"IIT_Hyderabad/CSE"` or `"IIT_Hyderabad/NH1"`.

Groups with fewer than `CAMPUS_MIN_GROUP_SIZE` (default 3) participants are privacy-suppressed.

---

## 12. Input / Output Structures

All public methods return plain Python `dict` or `list[dict]`. They are ready for:
- `jsonable_encoder()` in FastAPI
- Direct `json.dumps()`
- Pydantic model validation via `schemas.py`

```python
from carbon_coach.schemas import ChatResponse, ActivitySummary
# Validate/type-check a response:
resp = ChatResponse(**result)
```

---

## 13. Error Handling

| Condition | Exception |
|---|---|
| Blank message or session_id | `ValueError` |
| ADK runner error (network, model) | `RuntimeError` |
| Invalid emission factor | `ValueError` |
| Negative quantity | `ValueError` |
| Unknown food/travel mode | `ValueError` |
| Duplicate idempotency key conflict | `ValueError` |
| Invalid period string | `ValueError` |

All tool errors are caught inside the agent and returned as `{"error": "..."}` in the tool result — the agent then explains the error to the user in natural language.

---

## 14. Concurrency Safety

- Each `CarbonCoachService` instance owns its own `Runner` and `session_service`.
- **Do not share a single `Runner` across concurrent FastAPI workers** with `InMemorySessionService`.
- For multi-worker deployments: use a persistent, network-accessible session service.
- SQLite activity storage uses WAL mode and busy timeouts (10 s) — suitable for light concurrent read/write.
- For Cloud Run with multiple instances: replace SQLite with Cloud SQL + a custom `BaseSessionService`.

---

## 15. Storage Configuration

### Development (default)
SQLite at `carbon_activities.sqlite3` (relative to project root). Suitable for local testing only.

### Production (Cloud Run)
Option A — Persistent volume:
```bash
CARBON_DB_PATH=/mnt/data/carbon_activities.sqlite3
```

Option B — Cloud SQL (recommended for multi-instance):
1. Implement a `BaseSessionService` backed by Cloud SQL.
2. Pass it to `CarbonCoachService(session_service=your_service)`.
3. Store activities in Cloud SQL by customising `activity_tracker.py`'s `db_path()`.

---

## 16. Running Tests

```bash
# All deterministic tests (no API key needed):
python -m pytest tests/ -m "not integration" -v

# All tests including live agent (requires GOOGLE_API_KEY):
python -m pytest tests/ -v

# Specific module:
python -m pytest tests/test_carbon_engine_extended.py -v

# CLI demo (requires GOOGLE_API_KEY):
python scripts/demo_agent.py
```

---

## 17. Known Limitations

| Limitation | Details |
|---|---|
| **No Indian bus factor** | Generic 'bus' is blocked. Only `uk_bus` (UK reference) available. User must consent to using a foreign reference. |
| **InMemory sessions lost on restart** | Use a persistent session service for production. |
| **SQLite single-file** | Not suitable for multi-process Cloud Run. Use Cloud SQL in production. |
| **Food mass only** | Food inputs require mass in kg. Meal counts, portions, or calories are not supported without user-provided mass. |
| **Appliance inference** | kWh must be provided directly, or watts + hours via `appliance_to_kwh`. Gemini never infers kWh from "4 hours of AC". |
| **UK bus ≠ India bus** | The UK local bus factor is not representative of Indian buses. The agent warns users. |
| **CO₂ + CO₂e not addable** | Different gas types and accounting boundaries are kept in separate buckets. |

---

## 18. Google Cloud Permissions

For Vertex AI mode (`GOOGLE_GENAI_USE_VERTEXAI=TRUE`):

| Permission | Purpose |
|---|---|
| `aiplatform.endpoints.predict` | Gemini model inference |
| `aiplatform.models.get` | Model metadata |

For standard API key mode: no GCP permissions needed; only `GOOGLE_API_KEY`.

For Cloud SQL (if replacing SQLite):
- `cloudsql.instances.connect`
- `cloudsql.databases.get`

---

## Minimal End-to-End Example

```python
import asyncio
from carbon_coach.service import CarbonCoachService

async def main():
    service = CarbonCoachService()
    await service.start()

    session_id = "demo-session-001"
    user_id = "alice@example.com"   # pre-authenticated

    # Step 1: Log electricity
    r1 = await service.chat(
        "I used 5 kWh of electricity today. Log it.",
        session_id, user_id
    )
    print("Reply:", r1["reply"])
    print("Tools called:", r1["tool_calls_made"])

    # Step 2: Ask for weekly summary
    r2 = await service.chat(
        "How much CO2 did I log this week?",
        session_id, user_id
    )
    print("Reply:", r2["reply"])

    # Step 3: Get recommendations
    recs = service.get_recommendations(user_id, session_id)
    for r in recs:
        print(f"  • {r['title']}: {r['explanation'][:80]}...")

    await service.stop()

asyncio.run(main())
```

Expected: `log_electricity` tool is called, `3.55 kg CO2` is computed using the India FY2024-25 grid factor, and a reduction recommendation is generated.
