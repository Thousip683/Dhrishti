# Dhrishti Agent and Application Integration

The agent code from Thousip683/Dhrishti is combined with the Carbon Coach frontend and transactional backend. The runtime has one coordinator, a Tracker specialist and a Coach specialist. Chat and manual entry use the same authenticated session, approved factor registry and activity ledger.

## Source and preservation

Imported repository: git@github.com:Thousip683/Dhrishti.git

Source commit: 2e9ed024b50d4a1f56305001da87336a5b9ce45e

The original agent modules are retained under carbon_coach/reference_agent. Original tests are retained under tests/reference_agent with their imports adjusted to that namespace. Original handoff documents and setup files are archived under docs/upstream. The preserved CLI is scripts/demo_reference_agent.py. Existing Git history is retained as the parent of the combined project.

The active agent factory in carbon_coach/agent.py uses the imported coordinator and specialist templates and adapts their tools to carbon_coach/tools.py. It does not open the imported standalone SQLite ledger. The compatible food-mass comparison tool reuses the imported comparison engine, verifying its factors against the approved application registry before reporting results.

## Runtime entry points

- Application and integrated chat: uv run uvicorn carbon_coach.api:app --host 127.0.0.1 --port 8001, then open /chat.
- Agent factory: carbon_coach.agent.build_agent.
- Backend adapter: carbon_coach.adk_gateway.ADKGateway through the AgentGateway protocol.
- Optional ADK development UI: uv run adk web --host 127.0.0.1 --port 8000 --session_service_uri memory:// carbon_coach.

The ADK development interface is a separate debugging session store. Use the integrated application chat when manual and conversational activities must appear together.

## Shared ownership and persistence

FastAPI validates the session credential before invoking the gateway. The authenticated session ID is supplied as both the ADK user and session scope; no user-controlled identity is taken from message text. Tools receive the owned ledger through ToolContext and return structured calculation or activity receipts. The API commits the ledger, chat history and idempotency response in its transaction.

The gateway returns only newly committed activity IDs. A repeated message request with the same idempotency key returns its stored result rather than rerunning the agent. Confirmed partial writes are reported if a provider turn fails. Quantitative final replies are assembled from tool receipts, so generated prose cannot introduce an unsupported numerical claim.

Chat history is stored in the application's durable session context. A new gateway reconstructs recent conversational text from that history and retrieves calculation IDs from owned tools when needed. Raw nested ADK state-delta events are not stored recursively. Full asynchronous job recovery and multi-instance conversation scheduling remain later operational work.

## HTTP additions

POST /api/v1/sessions/{sid}/messages accepts text and an optional language value of en, hi or te. Its response contains status, reply, message_id, newly committed activity IDs, warnings and tool_calls. GET on the same path retrieves the authenticated session's transcript. Browser requests use the same HttpOnly cookie and CSRF controls as manual logging.

The frontend stores a pending message and retry key in sessionStorage without credentials. Unknown outcomes retain the same operation for retry, including after refresh. Confirmed replies refresh the transcript, history, summary and reduction queries. Assistant content is rendered as text, never arbitrary HTML.

## Factors and compatibility decisions

The imported catalog includes India electricity expressed as CO2, indicative India transport references and additional food factors. Those entries are preserved with their original modules but are not automatically promoted into the live CO2e registry. The application continues to use verified UK references and the approved global food averages. It does not relabel CO2 as CO2e, silently substitute regions, or expose unsupported transport modes.

The live Tracker supports current manual-entry categories and explicit quantities. Coach recommendations use actual application logs. Equal-mass food comparisons currently support approved rice, poultry and peas and disclose that mass is not nutritional equivalence. The upstream campus analytics implementation remains reference-only until consent, ownership and normalized comparison rules are implemented in the app.

English, Hindi and Telugu requests can select their reply language. Core estimate, saved, summary and clarification receipts have deterministic localized templates; detailed source and audit explanations can remain in English. Provider inference quality requires separate live evaluation.

## Configuration

Keep GOOGLE_API_KEY in the root ignored .env or server environment. GEMINI_MODEL remains supported. CARBON_GEMINI_MODEL, used by the imported code, overrides it when explicitly configured. No secrets are copied from the local .env into Git. GATEWAY_MODE=mock enables a clearly labeled development adapter without provider calls.

Use uv sync --frozen for the locked Python environment, or install the generated requirements.txt. Build the frontend with pnpm install --frozen-lockfile and pnpm build in frontend. Apply uv run alembic upgrade head before starting the application. No additional SQL migration is required for the transcript because it uses the existing session context.

## Verification

Run uv run pytest -q for application and preserved deterministic upstream tests. Live upstream tests are marked integration and excluded by default; explicitly use -m integration only with provider access and an intended live test run. The new combined-agent test exercises real ADK handoffs with a scripted model, shared manual/chat records, safe numerical rendering, compatible food comparison, Hindi clarification and gateway restart. It verifies that the standalone upstream activity database is never created by the live application path.

Frontend checks are pnpm test, pnpm build and pnpm test:e2e. Real-browser tests cover integrated chat transcript restoration in addition to manual logging and browser session flows. Scripted and mock tests do not claim that a live Gemini key or quota has been validated.
