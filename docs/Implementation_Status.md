# Carbon Coach Implementation Status

Updated 30 October 2026. Work follows Carbon_Coach_Frontend_Backend_Implementation_Plan.md. Stages 0 through 3 kept agent work separate. The subsequent user-authorized Dhrishti integration combines the coordinator and specialist agents with the application ledger.

| Stage | State | Evidence |
| --- | --- | --- |
| 0 Contract alignment | Complete | Named Pydantic schemas, generated TypeScript and OpenAPI, reproducible fixtures, screen map, contract gap list, AgentGateway with explicit mock, ownership-protected detail endpoints |
| 1 Durable backend foundations | Complete | SQLAlchemy repositories, Alembic baseline, normalized records, decimal columns, factor snapshots, transactional idempotency, correction history, lifecycle constraints, expiry cleanup and PostgreSQL row locking |
| 2 Frontend shell and sessions | Complete | React UI, responsive navigation, cookie sessions, CSRF and origin checks, idempotent browser bootstrap, settings, erasure and same-origin serving |
| 3 Activity forms | Complete | Four category forms, source-backed previews, appliance conversion evidence, explicit saving, draft recovery and duplicate prevention |
| 4 Dashboard | Next | Period selection, category breakdown, daily trends and coverage details |
| 5 to 9 | Pending | Full history management, insights, chat transport hardening, verification and deployment |
| 10 Optional extensions | Deferred | Campus mode, accounts, multilingual UI and additional factor regions |

## Stage 0 verification

Every JSON success route has a named response schema. Shared errors cover domain, request validation, unknown routes and unexpected failures. Date filters are validated. Activity and calculation detail routes verify session ownership. The application chat gateway can be mocked without a provider call. Newly committed IDs exclude existing records.

Generated artifacts are refreshed by `python scripts/export_contract.py`; use `--check` in CI. Development fixtures are marked as mock data and validated against response schemas. The stage completed with 24 passing tests before persistence work began.

## Stage 1 verification

Durable API storage defaults to a local SQLite database after migrations. PostgreSQL is selected with DATABASE_URL. Every session request uses a database transaction; ledger changes and idempotency responses commit together before success is acknowledged. SQLite serializes writes. PostgreSQL uses a session-row NOWAIT lock; busy clients retry the same mutation key. No process-local lock is used as the only database coordination mechanism.

The baseline migration matches SQLAlchemy metadata on both databases. Tests exercise restart recovery, persistent retry responses, concurrent same-key submissions, correction lineage, superseded-calculation rejection, rollback, expiry, ownership, revision conflicts and cascading erasure. Database work runs outside the event loop during lock acquisition and commit.

The standard suite completed with 31 passing tests. The complete suite with PostgreSQL integration enabled completed with 38 passing tests, including 14 storage cases across SQLite and PostgreSQL. PostgreSQL tests used a disposable PostgreSQL 18 cluster on localhost and a separate temporary database per case. The test server was stopped afterward. This tested the repository and API request path; it is not a cloud deployment, load test or live agent evaluation.

## Setup

1. Run `uv sync --frozen`.
2. Configure `.env` from `.env.example` without replacing an existing secret file.
3. Run `uv run alembic upgrade head`.
4. Run `uv run uvicorn carbon_coach.api:app --host 127.0.0.1 --port 8001`.
5. Check `/readyz`, then use `/docs` or the API.

Default configuration is STORAGE_MODE=database and DATABASE_URL=sqlite:///./carbon_coach.db. Set STORAGE_MODE=memory explicitly for disposable development. The local database file is excluded from Git. The background retention sweep runs every minute; direct access to an expired session is rejected immediately. Actual cleanup can occur on the next sweep after the inactivity deadline.

## Stage 2 verification

The custom React TypeScript frontend uses Vite, React Router and TanStack Query. It includes welcome and timezone setup, responsive navigation, backend-driven overview statistics, basic activity history, source disclosure and session settings. Manual entry and full insights remain explicitly pending for their later stages. No sample activities or invented dashboard totals are displayed.

Browser credentials use HttpOnly SameSite cookies. Cookie mutations require an allowed origin and CSRF token; direct bearer clients remain supported. Browser bootstrap is transactionally idempotent. Sessions restore after refresh, timezone changes preserve historical activity dates, and erasure clears cookies, application query state and drafts. Successful activity requests refresh the frontend's inactivity deadline from a server response header.

Migration 0002_browser_sessions adds hashed browser bootstrap records. Durable browser restoration and creation replay were tested after repository restart against SQLite and PostgreSQL. Current verification: 45 backend tests with both database variants enabled, 8 frontend unit tests, 6 real Chrome browser tests across desktop and mobile, and a successful TypeScript and production build. Desktop and mobile overview, welcome and settings screenshots were reviewed. The remaining test-run warning is an upstream Starlette test-client deprecation notice.

The built application runs at http://127.0.0.1:8001, with API documentation at /docs. See Stage_2_Browser_API.md for cookie and endpoint details. Agent prompts and tools were not modified.

## Stage 3 verification

Manual logging is complete for travel, electricity, food and waste. The backend supplies approved choices, recipe definitions, technical limits and the session-local current date. Forms preview without logging, invalidate old previews on edits and save only explicit server-owned calculation IDs. Appliance conversions require an input-power basis, retain conversion evidence and cannot be reused with forged kWh or another session's ID. Explicit factor versions are validated rather than silently substituted.

Drafts and request keys survive navigation and refresh. An unconfirmed save freezes its original payload and can be retried safely. Browser tests simulated the actual server committing while the response was lost and verified that retry produced one record. Successful saves refresh history, overview and reduction query state. Food assumptions require agreement, and unsupported regional factors or waste routes are not offered as valid estimates.

Current verification: 48 backend tests in the standard run, 57 with PostgreSQL storage variants enabled, 15 frontend unit tests and 14 desktop/mobile browser tests. TypeScript and production builds pass, generated contract artifacts match source, and calculation-preview layouts were visually reviewed. See Stage_3_Activity_Logging.md for endpoint and recovery details. The local application is available at http://127.0.0.1:8001/log.

## Operational limits and next work

Full period dashboards, filtered history and editing interfaces, pagination, comparison windows, scheduled request recovery, rate limits and deployment are still pending in their planned stages. Browser session bootstrap is idempotent; the raw bearer-session creation endpoint has no bootstrap extension yet. Whole-session snapshots are loaded for repository operations in this first durable version; optimize filtered reads as history grows. PostgreSQL locking serializes work per session, including a chat turn, and long-running chat recovery is a Stage 7 concern.

Application records persist across restarts. The existing ADK adapter still keeps its conversation context in memory; this work deliberately did not redesign agent memory. The ADK development UI and custom API remain separate session stores. Readiness checks database schema availability; provider availability is a separate health concern.

No previous in-memory API session is automatically migrated into the new database. Start a new API session after switching storage modes. Existing source factor versions remain unchanged.

## Dhrishti repository integration

The upstream agent source from Thousip683/Dhrishti at commit 2e9ed024b50d4a1f56305001da87336a5b9ce45e is preserved in carbon_coach/reference_agent, with original tests under tests/reference_agent. The active coordinator, Tracker and Coach use shared application tools and records. A compatible food comparison reuses the upstream calculation engine after checking approved factor values. Indicative and CO2-only upstream factors remain isolated from live CO2e totals.

The /chat page now uses the same authenticated browser session as manual forms. Transcript storage, request replay, newly committed IDs, tool evidence and conversation restoration are integrated. English, Hindi and Telugu core receipts are supported, with some audit details in English. This does not complete the later asynchronous job scheduling, quota management or cloud-deployment stages. Full integration details are in AGENT_INTEGRATION.md.

Integration verification: 201 backend tests passed with PostgreSQL variants enabled (6 live-provider cases excluded), 15 frontend unit tests and 16 desktop/mobile browser tests passed. TypeScript and production builds passed. Live Gemini inference remains unverified after provider timeouts; deterministic tests exercise the real ADK handoff and tool loop without network calls.
