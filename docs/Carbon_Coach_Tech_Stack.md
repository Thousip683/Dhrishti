# Carbon Coach Technical Stack and Architecture

Version 1.0 | 30 October 2026 | Proposed implementation

## Technical decision

Build Carbon Coach as one Python application with Google ADK and Gemini for conversation, deterministic Python services for calculations, and a versioned emission-factor registry. Start with the ADK development interface and session memory to meet the three-hour limit. Add a FastAPI facade and durable storage when shipping the custom web interface or Cloud Run deployment.

This stack supports the accompanying PRD and API contract. It is a recommended design, not a claim that these components are already implemented. Avoid making optional deployment or multi-agent work a dependency of reliable calculations.

## Selected components

| Layer | MVP choice | Reason and extension |
| --- | --- | --- |
| Runtime | Python 3.12 | Suitable baseline for typed domain services; verify package compatibility in setup |
| Agent framework | Google ADK Python | Required by challenge; tool calls and session context |
| Language model | Available stable Gemini text model with function calling | Required provider; exact model ID selected by configuration and smoke test |
| Model access | Gemini Developer API server-side | Fast initial setup; Vertex AI is a deployment option |
| Validation | Pydantic v2 compatible with resolved ADK dependencies | Discriminated input models and strict validation |
| Arithmetic | Python decimal and zoneinfo | Deterministic math, rounding and local calendar windows |
| Factor registry | Versioned JSON files in source control | Reviewable provenance and no runtime network dependency |
| Local UI | ADK development web interface | Fastest path to demonstrable agent behavior |
| Application API | FastAPI and Uvicorn when custom UI is enabled | Typed REST facade and generated OpenAPI |
| Custom UI | Server-rendered HTML with small JavaScript module | Avoid a second build toolchain for a three-hour build |
| Local persistence | InMemorySessionService plus application repository | Explicit restart loss; optional SQLite for single-process local persistence |
| Hosted persistence | PostgreSQL through a supported driver and SQLAlchemy | Durable logs, transactions, idempotency and multi-instance safety |
| Tests | pytest plus ADK evaluations | Deterministic arithmetic and conversational tool trajectories |
| Packaging | uv with lockfile and a slim Python container | Reproducible installation and deployment |
| Hosting | Cloud Run as a bonus | Container service with managed HTTPS |
| Secrets | Local ignored environment file; Secret Manager in cloud | Credentials stay out of code, UI and container image |

Do not pin a guessed latest ADK or Gemini version in this document. Resolve compatible packages during implementation, commit the lockfile and record the exact tested model ID. Prefer a stable model over a preview dependency for the demo. Model selection must verify function calling, quota and availability for the team's account.

## Architecture and request flow

Browser sends a message to the application facade. The facade validates the session credential and idempotency key, acquires session coordination and runs ADK. Gemini identifies candidate activities and invokes tools. Tools call one shared domain service. That service normalizes units, selects approved factors, calculates results, stores receipts and commits explicitly logged activities. The response renderer uses tool evidence to create the activity receipt, totals or suggestions.

```text
Browser or ADK development UI
            |
Session authorization and request coordination
            |
ADK agent using Gemini
            |
Typed Python tools
            |
Calculation and logging domain services
       /                    \
Versioned factor registry    Session and activity repository
            |
Structured claims and deterministic response rendering
```

The API facade is optional for the development UI, but the domain services are shared in both paths. The UI formats values; it does not calculate emissions. Gemini interprets and explains; it never supplies emission factors from memory.

## Agent design

Use a single root Carbon Coach agent for the MVP. Instructions require tools for numerical claims, clarification for missing quantities, and a clear distinction between hypothetical calculations and logs. Give tools narrow typed inputs and informative descriptions. Inject server date, timezone, request identity and known preferences through trusted context.

Optional Tracker and Coach agents share the domain repository. Tracker parses, calculates and logs; Coach reads summaries and computes alternatives. A coordinator controls handoff and response assembly. Only one logging service may write a given activity. Do not let two agents independently record the same user statement. This bonus is valuable only after single-agent correctness passes.

Conversation history is not the accounting ledger. Summaries read structured activities. Store a pending clarification record with candidate index, provided values and missing fields so “1.5 kW” can resolve the relevant AC item without duplicating the completed bus entry.

## Domain modules and repository layout

```text
carbon_coach/
  agent.py                 ADK root agent and instructions
  tools.py                 Thin typed ADK tool wrappers
  api.py                   Optional FastAPI facade
  config.py                Validated runtime configuration
  domain/
    models.py              Calculation and activity schemas
    calculations.py        Decimal arithmetic and unit conversions
    factors.py             Registry loading and compatibility
    ledger.py              Log, correction and deletion operations
    summaries.py           Periods, aggregation and comparisons
    recommendations.py     Compatible alternative scenarios
    claims.py              Numerical evidence and safe rendering
  repositories/
    memory.py              Local session implementation
    database.py            Durable implementation
  data/
    factors.json           Approved sourced factor records
    recipes.json           Serving definitions and ingredient factors
  static/                  Optional browser client
tests/
  fixtures/                Synthetic factors and fixed clocks
  unit/                    Deterministic correctness
  integration/             Sessions, retries and ownership
  evals/                   Golden conversations
docs/                      PRD and API contract
pyproject.toml
uv.lock
Dockerfile
.env.example
.gitignore
```

Keep HTTP handlers, ADK tools and arithmetic separate. A tool wrapper validates context and delegates to a service. That service is independently testable without Gemini or a network connection.

## Data model and storage

Session stores ID, token hash, timezone, locale, region, creation and expiry timestamps and revision. Calculation stores normalized inputs, formula, factor snapshots, decimal result, assumptions, warnings and claim IDs. Activity references one calculation and stores local date, optional note, revision and deletion metadata. Scenario references baseline activities plus alternative calculation evidence. RequestRecord stores an idempotency key, payload hash, processing state and final response.

Use numeric database columns with fixed precision and scale for emissions and quantities; a proposed numeric(20,6) supports the technical input limits. Factor versions and calculation receipts are immutable. Corrections replace the active reference rather than rewriting evidence. Store audit timestamps in UTC and activity dates as local calendar dates.

ADK session state holds conversation context and pending items. The application ledger is authoritative. If ADK session persistence and the ledger use different stores, a committed ledger receipt must allow recovery after a partial conversation failure. Do not assume ADK state mutation and a separate database write form one atomic transaction.

Memory mode uses a per-session lock and loses all data on restart. SQLite is acceptable for a local single-process demo. Cloud Run requires durable external storage: neither an in-memory session nor a local SQLite file provides reliable cross-instance history. Use a supported ADK database session backend after compatibility testing, or explicitly persist application context through a custom session adapter.

## Factor engineering

Curate a small approved registry rather than dynamically searching for factors during conversation. Each entry contains value, denominator, gas basis, lifecycle boundary, geography, year, dataset version, exact source locator and limitations. Preserve a registry release identifier in each calculation.

Review travel factors for passenger-km versus vehicle-km. Review electricity for regional applicability and CO2 versus CO2e. Review food for ingredient mass and recipe serving sizes. Review waste for treatment routes and recycling-credit assumptions. Reject mixing incompatible boundaries in one comparison. Never copy synthetic fixtures into the approved registry.

Suggested source candidates are the UK government conversion-factor collection for travel and waste, the CEA power-sector database for India electricity subject to gas-basis validation, and the Poore and Nemecek food dataset accessible through Our World in Data. A source candidate does not approve a numeric value. Record the exact verified row before exposing its factor.

## Numerical grounding

Use Decimal from validated strings. Normalize units before multiplying. Persist six decimal places and format two for display; aggregate before formatting. Compute percentages, totals and savings in tools. The claims service produces a typed evidence record for each derived number.

For reliable display, render activity receipts, total cards and quantified tips directly from structured tool results. Let the model provide optional nonnumeric explanatory prose. Validate any numerical claim in generated prose against evidence, or fall back to a deterministic response. Do not rely solely on a prompt saying “never invent numbers.”

## Configuration and secrets

| Configuration | Meaning |
| --- | --- |
| GEMINI_MODEL | Exact tested Gemini model ID |
| GOOGLE_API_KEY | Developer API secret, server-side only |
| MODEL_BACKEND | developer_api or vertex; one configured path |
| GOOGLE_CLOUD_PROJECT | Required for cloud services and Vertex mode |
| GOOGLE_CLOUD_LOCATION | Configured region for the chosen provider |
| DATABASE_URL | Durable store connection when database mode is enabled |
| STORAGE_MODE | memory or database |
| DEFAULT_TIMEZONE | Asia/Kolkata unless explicitly changed |
| FACTOR_REGISTRY_PATH | Versioned approved factor file |
| SESSION_TTL_HOURS | Proposed default 24 |
| ALLOWED_ORIGINS | Explicit browser origin allowlist |
| PORT | HTTP listener port supplied by Cloud Run |

These application settings are proposed names; map them to the exact installed ADK provider configuration during implementation. Vertex mode uses application default credentials or a service account, rather than an embedded Developer API key. Never ship real credentials in .env.example.

## Dependency and setup strategy

Initialize a Python 3.12 environment. Add google-adk and compatible pydantic dependencies, then fastapi and uvicorn if using the facade, pytest for tests and database packages only for the selected persistence mode. Commit uv.lock after a successful import, minimal tool-call and session smoke test. Use uv sync --frozen for reproducible setup.

Suggested local commands after implementation are uv run pytest, uv run adk web from the parent of the agent package, or uv run uvicorn carbon_coach.api:app --host 127.0.0.1 --port 8000 for the custom facade. Confirm installed CLI flags with its help output before documenting deployment commands as tested.

When adapting Campus Buddy, replace its Groq LiteLLM configuration with native Gemini access, replace sample campus lookup tools with the shared calculation services, and replace reminder state with a typed activity ledger. Do not retain old evaluation examples as Carbon Coach evidence. This document does not authorize or claim that migration has already occurred.

## Cloud Run deployment design

Build a non-root container with dependencies installed from the lockfile. Bind the server to 0.0.0.0 and the PORT environment variable. Expose liveness and readiness paths. Pass secrets through Secret Manager and grant the service account only the required storage and secret access. Configure explicit origins and a rate-limited anonymous session flow for the demo.

Use an external PostgreSQL database for persistent sessions and ledger data. Apply migrations before directing traffic. Limit initial maximum instances and model request concurrency to account quota; these are settings to measure and tune, not a promise of performance. A single instance still needs durable storage to survive restarts. Budget alerts are monitoring signals, not hard spending caps.

Deploy only after the local demo passes. Verify HTTPS, cold-start behavior, model access, storage connectivity, session isolation and restart persistence. Keep the last working container revision available for rollback. The exact project, region, service name and deployment permissions are team-specific and must be supplied during implementation.

## Security and privacy controls

Treat user messages as untrusted input and disallow prompt-controlled session selection, factor edits, external URL fetching or shell execution. Tools require trusted context for authorization. Validate all quantities and request sizes, rate-limit creation and model calls, and serialize or transactionally coordinate session writes. Use revision checks and idempotency keys.

Avoid logging raw messages by default. Log request IDs, tool names, duration, error codes, factor releases and anonymous session references. Never log tokens or API keys. Enforce the configured expiry cleanup and session erasure. A public endpoint must not expose another user's history through enumerable IDs.

## Test and evaluation strategy

Unit tests cover exact fixture arithmetic, occupancy, meal recipe sums, energy conversions, waste routes, finite input validation, rounding, date boundaries and savings. Integration tests cover session ownership, duplicate requests, atomic correction, deletion, summary consistency and partial model failures. Test durable mode with multiple workers before claiming Cloud Run scaling support.

Golden ADK cases inspect expected tool use plus final claims. Include the bus and AC clarification, four categories, empty memory, weekly summary, zero comparison baseline, unsupported activity, correction, hypothetical calculation and attempts to force fabricated totals. Add Hindi and Telugu cases only when that feature is actually enabled.

Use synthetic factors for deterministic tests and separately verify real registry provenance. Golden reference text is not a substitute for calculation assertions. Record actual pass counts, median and p95 latency, and tool-call errors from the final demo build.

## Observability and failure recovery

Record structured events for request accepted, tool started, tool completed, activity committed and reply completed. Include a correlation ID throughout. Track calculation failures, clarification frequency, model latency, duplicate-write prevention and unsupported factor requests. Expose readiness based on local registry and storage, not an expensive model call for every probe.

Retry transient model failures with bounded exponential backoff and provider retry guidance. Never repeat committed writes. Store processing request state so the API can return 202 and be polled. If evidence validation fails, return a safe template. If storage is unavailable, do not claim an activity was saved.

## Delivery milestones and tradeoffs

First complete deterministic calculations and evidence. Then connect ADK and memory. Next add summaries, scenarios and golden cases. Add custom API and hosting only when they preserve the working core. One agent reduces handoff complexity; a small JSON registry reduces data integration risk; the built-in interface reduces frontend effort. These choices fit the hackathon but should evolve before a public long-term service.

After the event, prioritize accounts and retention controls, stronger provenance review, operational monitoring, durable history and accessibility. Add campus comparisons only after consent, denominator and coverage rules are implemented. Avoid publishing raw leaderboards built from incomplete voluntary logs.

## Official documentation and source candidates

- Google ADK framework and component guidance: https://adk.dev/
- ADK Python source and release compatibility: https://github.com/google/adk-python
- ADK Cloud Run deployment guide: https://github.com/google/adk-docs/blob/main/docs/deploy/cloud-run.md
- Gemini models and capability selection: https://ai.google.dev/gemini-api/docs/models
- Cloud Run container runtime contract: https://docs.cloud.google.com/run/docs/container-contract
- UK government factor datasets: https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
- CEA baseline database reports: https://www.cea.nic.in/cdm-co2-baseline-view?heading=CDM-CO%E2%82%82+Baseline+Database+Reports&lang=en&mappingId=234
- Food dataset access and underlying research attribution: https://ourworldindata.org/grapher/ghg-per-kg-poore

Official framework and runtime references were checked during document preparation. Package versions, quotas, model access and emission dataset rows still require project-specific validation before deployment.
