# Carbon Coach Frontend and Backend Implementation Plan

Version 1.0 | 30 October 2026

## Purpose and boundary

Build the application around Carbon Coach in reviewable stages: a usable frontend, durable backend, reliable activity tracking, transparent results and a deployable service. Agent prompts, Gemini model selection, agent tools, multi-agent orchestration and agent evaluations are outside this plan. The chat transport and the application interface to an agent are included so frontend and backend work can proceed with a deterministic mock adapter.

The plan extends the current local prototype. It does not restart implementation or claim that the target features already exist. Each stage ends with observable behavior and a verification gate. Complete the core application before taking on optional campus, account or language features.

## Current baseline

Already present: FastAPI routes for sessions, factor evidence, calculations, logging, activity lists, edits, deletes, summaries, reductions and messages; decimal calculation services; an in-memory repository; generated OpenAPI; dependency lockfile; and an automated test suite. The last recorded implementation run passed 20 tests. Existing correction and deletion behavior should be preserved through the persistence migration.

The current chat screen is the ADK development interface. There is no custom application frontend. The API is single-process and loses its session data on restart. Session creation is not yet idempotent; lists lack pagination; comparison periods and durable request recovery are absent. API behavior is a subset of the target contract. Live provider availability must not block frontend development.

The available factors currently cover UK travel, electricity and waste references and global food averages. The UI must disclose this and must never label them as India-specific estimates. Additional regions are a separate reviewed data task.

## Proposed application stack

| Area | Choice | Purpose |
| --- | --- | --- |
| Frontend | React with TypeScript and Vite | Separate application UI with typed API integration |
| Navigation | React Router | Dashboard, logging, history, insights, sources and settings |
| Server state | TanStack Query | Fetching, caching, invalidation and request state |
| Forms | React Hook Form with schema validation | Accessible category forms and field errors |
| Styling | CSS variables and scoped component styles | Small consistent design system without a heavy theme dependency |
| Charts | Small SVG charts with accessible data tables | Daily trend and category breakdown, displaying backend values |
| Backend | Existing FastAPI with Pydantic | Preserve Python services and generate OpenAPI |
| Persistence | SQLAlchemy, Alembic and PostgreSQL | Transactions, migrations, history and multi-instance operation |
| Local development | SQLite option plus PostgreSQL integration environment | Simple local start; verify production semantics against PostgreSQL |
| Frontend tests | Vitest and React Testing Library | Form, state and component behavior |
| Browser tests | Playwright | Full application journeys and responsive behavior |
| Backend tests | Existing pytest plus database integration tests | Calculation invariants, ownership and recovery |
| Deployment | One Cloud Run service serving built frontend and API | Same origin, one deployable artifact and simpler session handling |

This is a proposed expansion from the original lightweight HTML option. React is justified here by the requested full application: multiple screens, filtered history, reusable forms and long-running request states. Exact compatible package versions must be selected, tested and locked during Stage 2; do not install unpinned moving dependencies in deployment.

Vite supplies the frontend development and production build workflow. TanStack Query manages remote state; calculation rules remain on the backend. Alembic supplies database migration tooling for SQLAlchemy. See the official references at the end of this document.

## Application screens

| Screen | Required content | Important states |
| --- | --- | --- |
| Welcome and session setup | Scope, reference region, timezone and start action | Creating, creation failure, returning session, expired session |
| Dashboard | Logged total, period selector, categories, daily trend, coverage and recent entries | Loading, empty, partial coverage, API error |
| Log activity | Travel, electricity, food and waste forms; preview then save | Invalid field, missing factor, preview stale, saving, saved |
| Activity history | Date and category filters, paginated list, edit and remove | No matches, page loading, revision conflict, deletion failure |
| Insights | Backend-produced comparisons and reduction scenarios | No baseline, zero baseline, incompatible factors, no eligible suggestions |
| Chat | Message list, composer, status and structured receipts | Mock adapter, unavailable agent, queued, clarifying, partial completion |
| Sources | Factor evidence, recipe definitions, units and boundaries | Supported registry, unavailable version, unsupported region |
| Settings | Timezone, session expiry, privacy, erase session | Unsaved change, saving, erase confirmation, erased |

Dashboard, Log, History, Insights and Settings form the main navigation. Chat is an optional view during non-agent development. Sources can be a page reached from any result receipt. A small-screen navigation must preserve access to logging and history without hiding errors or coverage notes.

## Nonnegotiable application rules

- The backend owns quantities after normalization, emission factors, arithmetic, totals, percentages, savings, dates and coverage semantics. The frontend formats returned values without recomputing them.
- Show “logged emissions” and the exact period. Missing logs do not imply zero actual emissions.
- Previewing an estimate does not save it. Saving is a distinct acknowledged operation.
- Editing or deleting a record must update dashboard, history and insights together after the server confirms the mutation.
- Unknown outcomes after a timeout require retry with the same idempotency key or request-status recovery. Never retry a mutation under a new key automatically.
- Hypothetical alternatives never reduce recorded totals. Mutually exclusive suggestions are not summed.
- Display the factor region, source, version and boundary through a result detail view. Never substitute an unsupported regional factor silently.
- Keep credentials server-side where possible. No Gemini key or database secret enters a frontend bundle, API response or browser log.

## Stage 0 Align contracts and define the delivery boundary

Goal: make frontend and backend agree on implemented behavior before changing either.

### Backend work

1. Compare actual FastAPI routes and generated OpenAPI with the target API document. Record each mismatch as implemented, required before demo or deferred.
2. Introduce named request and response models for every route. Keep decimal values as strings and timestamps and dates explicitly typed.
3. Define one error envelope including request ID, stable error code, retryability and field errors. Normalize framework errors and unsupported routes where appropriate.
4. Confirm inclusive start and exclusive end dates, Monday-based weeks and session timezone rules. Define how a timezone change affects historical local activity dates; proposed rule: preserve stored activity dates and apply the new zone only to future relative-date resolution.
5. Freeze the application-facing factor, activity, summary, comparison and reduction schemas. Add immutable calculation evidence detail retrieval if receipts cannot otherwise be reopened from history.
6. Define an AgentGateway interface with mock and real implementations. This stage defines inputs, status, evidence and committed record IDs only; it contains no agent implementation work.

### Frontend work

1. Map routes and sketch screen layouts for desktop and narrow mobile screens.
2. Define empty, loading, validation, error, offline and expired-session states for each screen.
3. Generate TypeScript API types from the frozen OpenAPI schema.
4. Create fixture responses for populated, empty and failed states. Mark all development fixture data as mock data.
5. Establish source-of-truth ownership: query cache for server data; local component state for drafts and dialogs.

Deliverables: contract gap checklist, typed schemas, frontend screen map and shared fixtures.

Completion gate: the team can trace every UI field to a documented response property; examples validate against schemas; no frontend feature depends on undocumented agent behavior.

## Stage 1 Establish durable backend foundations

Goal: preserve sessions and records across restarts with reliable mutations.

### Backend work

1. Extract repository interfaces from the current dictionaries. Keep calculation functions independent of HTTP and storage.
2. Add SQLAlchemy models and Alembic migrations for sessions, calculation receipts, activities, idempotency records, requests and optional message records.
3. Store tokens as hashes and emissions in fixed-precision numeric columns. Preserve immutable factor snapshots and the registry release associated with each calculation.
4. Add ownership constraints, indexes on session plus activity date and stable ordering fields, and uniqueness for committed calculations and idempotency scopes.
5. Make activity writes, revision updates and idempotency responses one transaction. Define explicit calculation lifecycle states such as uncommitted, active and superseded; do not allow old superseded calculations to be committed again.
6. Add configurable database connection management, migration startup guidance and readiness checks.
7. Implement per-session durable request coordination. Replace process-only locking before multiple workers or instances are enabled.
8. Add expiry cleanup that removes application and conversation data through an adapter. Expired reads must not merely remove a token while leaving the associated data indefinitely.

### Frontend work

Proceed independently with static screen layouts and fixtures from Stage 0. Show a placeholder persistence mode in the session notice; do not claim the database migration is complete until backend verification passes.

Deliverables: repository layer, migrations, local database setup and integration test harness.

Completion gate: create, calculate, log, restart and read the same record; concurrent duplicate commits produce one activity; stale edits are rejected; failed transactions leave no half-written activity.

## Stage 2 Build the frontend shell and session lifecycle

Goal: launch a real application that connects to the API.

### Frontend work

1. Create the React TypeScript application under frontend with development proxying to /api and a production build directory.
2. Establish typography, spacing, colors, buttons, inputs, dialogs, notifications, skeletons and accessible focus states.
3. Build application routes and navigation. Create responsive layouts at representative widths such as 360, 768 and 1280 pixels.
4. Implement a single API client handling credentials, request IDs, cancellation, normalized errors and idempotency keys.
5. Implement session creation, restoration, expiry and erasure. Keep an unfinished form draft during a recoverable network error without pretending it was saved.
6. Add a configuration indicator for mock chat or unavailable agent, while retaining fully usable manual logging.

### Backend work

1. Add idempotent session creation scoped to an anonymous bootstrap nonce with a bounded replay lifetime.
2. For the browser, use a secure HttpOnly session cookie through the same-origin service. Preserve bearer access for direct API clients. Document the cookie endpoint or credential exchange as an explicit contract extension.
3. Enforce SameSite policy and CSRF protection for cookie-authenticated mutations, including origin validation and a CSRF token where needed. Never put credentials into query strings.
4. Restrict development CORS to configured origins. Serve frontend assets and route fallback without intercepting /api, /healthz or /readyz.
5. Expose session metadata and a timezone update endpoint; make these contract additions explicit.

Deliverables: application shell, session integration and shared UI primitives.

Completion gate: a fresh browser starts a session; refresh restores it; expired credentials show a recovery action; erasure clears client caches and invalidates server access; all main navigation works with a keyboard.

## Stage 3 Deliver activity calculation and logging end to end

Goal: give users a complete non-agent path for all four categories.

### Frontend work

1. Build category forms using the backend's supported factor and recipe metadata rather than hardcoded unsupported choices.
2. Travel collects mode, distance and occupancy only when the selected factor requires it. Explain passenger versus vehicle allocation without asking the user to perform arithmetic.
3. Electricity collects measured kWh or average electrical input power plus hours and optional duty cycle. Show region support before submission.
4. Food displays the exact recipe masses and excluded items and requires a serving count. Waste collects material, mass and an allowed treatment route.
5. Submit for calculation and show a preview receipt with units, estimated emissions, source access, assumptions and a separate Save action.
6. Invalidate an old preview when any relevant input changes. Prevent saving stale or still-processing previews.
7. Preserve the same mutation key through retries and disable duplicate submissions while the outcome is pending.

### Backend work

1. Finish input and response schema parity for all calculation variants. Validate factor IDs and versions, supported regions, valid recipe definitions and category-specific caps.
2. Add an appliance-conversion endpoint returning conversion evidence. Link this evidence to the subsequent electricity calculation rather than losing it in the browser.
3. Require a real local activity date at commit time and reject future actual logs. Preserve hypothetical calculations separately.
4. Commit only server-owned calculation IDs. Enforce session ownership and calculation lifecycle uniqueness at database level.
5. Add a factor capabilities response exposing supported combinations, units, caps and missing regional support.
6. Retain source attribution and reject incompatible gas bases or boundaries instead of relabeling them.

Deliverables: working manual logging forms and durable calculation receipts.

Completion gate: each category can be calculated and saved; unsupported combinations fail clearly; calculation alone changes no total; lost responses and double clicks create one record; saved values match backend evidence exactly.

## Stage 4 Build dashboard totals and trends

Goal: make recorded activity understandable without misleading comparisons.

### Frontend work

1. Display today's or this week's logged total, category breakdown, number of recorded activities and logged-day coverage.
2. Add a period selector for today, week and custom dates. Keep date selection in the URL where useful for returning to the same view.
3. Render daily totals using backend buckets, with a distinct no-record state. Provide an accessible table equivalent.
4. Add recent activities and links to the relevant record and factor evidence.
5. Invalidate summary and recent-activity queries after saves, corrections and deletions. Guard against a slow response from a previous session or filter overwriting the current view.

### Backend work

1. Add consistent snapshot aggregation over active records and structured coverage metadata.
2. Implement server-resolved date windows with a fixed maximum length and timezone-aware boundaries.
3. Aggregate stored precision before display rounding. Return display-ready totals and chart values.
4. Include category boundary limitations and factor releases used within the period.
5. Add database indexes and query tests; measure performance before introducing a separate summary cache.

Deliverables: a usable dashboard backed by durable records.

Completion gate: dashboard totals equal active matching records; deleting or editing an entry refreshes all relevant views; midnight and Monday boundaries pass tests; an empty period never reads as a measured zero footprint.

## Stage 5 Complete activity history and record management

Goal: let users inspect and correct their data reliably.

### Frontend work

1. Add filters for date range and category with clear reset controls.
2. Add cursor-based pagination and retain filters while viewing record details.
3. Build a detail view with original inputs, normalized units, factor snapshots, assumptions, source links and timestamps.
4. Edit through the same forms used for logging, creating a replacement calculation before committing a correction.
5. Handle revision conflicts with a reload-and-review action. Never silently overwrite another edit.
6. Add deletion confirmation and visible completion. Do not offer Undo unless the backend supports a real restore operation.

### Backend work

1. Validate list filters and introduce bounded cursor pagination with deterministic ordering and snapshot semantics.
2. Return revision metadata on detail and list responses and enforce If-Match consistently.
3. Record correction lineage and superseded calculation state in one transaction.
4. Make repeated deletion safe without letting a deleted activity be recreated by replaying an old calculation.
5. Ensure erased sessions remove receipts, requests, cached responses and messages according to the declared retention policy.

Deliverables: complete history, evidence detail, correction and deletion workflows.

Completion gate: filters and pagination produce no duplicates or skipped records within a snapshot; stale writes fail safely; corrected totals update once; another session cannot inspect a record by guessing its ID.

## Stage 6 Add comparisons and insights

Goal: provide useful interpretation entirely from deterministic backend evidence.

### Frontend work

1. Show current and previous comparable windows, absolute change and percentage only when returned as available by the backend.
2. Explain partial periods, inadequate coverage, zero baselines and factor-version differences.
3. Display each reduction scenario with the original activity, alternative, assumptions and estimated saving for the stated period.
4. Group mutually exclusive alternatives and avoid a combined saving total unless the backend explicitly supplies an eligible non-overlapping total.
5. Show a useful empty state that invites logging rather than inventing advice or savings.

### Backend work

1. Add previous-equivalent comparisons, including partial-week rules and a defined current-day cutoff.
2. Return null percentages with machine-readable reasons for unavailable or zero baselines.
3. Expand the scenario service to accept period filters and user constraints while retaining compatible quantities and boundaries.
4. Return overlap groups, complete factor evidence and assumptions in each scenario.
5. Do not infer recurrence or annual savings from a single log. Require an explicit scenario frequency when extrapolation is added.

Deliverables: evidence-backed comparisons and reduction cards.

Completion gate: every displayed change and saving matches backend output; no missing-baseline percentage is rendered; scenario creation leaves actual totals unchanged; incompatible alternatives are excluded or explained.

## Stage 7 Build chat transport independently of agent internals

Goal: support a future agent integration while keeping application development unblocked.

### Frontend work

1. Build the message transcript, composer, send status and accessible status announcements.
2. Render structured calculation receipts, committed activity links and clarification fields from the application contract.
3. Support pending, processing, completed, needs clarification, partial failure, failed and cancelled states.
4. Recover pending requests after refresh using their server request IDs. Disable a new conflicting turn only for the same session while preserving the visible draft.
5. Show agent unavailability without breaking manual logging, history or dashboard access.

### Backend work

1. Implement the gateway boundary defined in Stage 0 using a deterministic mock adapter first.
2. Persist request lifecycle state, idempotency fingerprint, resulting receipts and only the activity IDs committed by that turn. The current API's list of all active IDs must not be labeled as newly committed IDs.
3. Implement the target 202 processing response and request-status endpoint. Establish one authoritative request record across retries and workers.
4. Define how a worker resumes or safely fails interrupted work. Persist checkpoints where supported; never blindly restart a run that may already have committed activities.
5. Bound execution time, handle disconnects and cancellation, and distinguish stopping generation from rolling back already committed logs.
6. Keep partial commits visible and invalidate affected dashboard queries when receipts confirm a write.

AgentGateway input: authorized session reference, request ID, user message, locale, trusted date context and application read/write capabilities. Output: status, structured receipts, clarification requests, evidence IDs, newly committed activity IDs and normalized errors. Agent prompts, tool selection and model behavior remain a separate workstream.

Deliverables: mock-powered chat experience and durable transport protocol ready for an agent adapter.

Completion gate: mocked delayed completion, clarification, partial failure, cancellation and duplicate delivery all render correctly; refresh recovers status; unavailable agent does not block the rest of the product.

## Stage 8 Harden and verify the complete application

Goal: make the app safe and predictable for a public demo or limited pilot.

### Frontend work

1. Complete keyboard and screen-reader checks, focus restoration and non-color status cues.
2. Test every screen at narrow mobile widths, with long labels, large text and slow connections.
3. Test loading, empty, stale, validation, offline, rate-limited, expired-session and partial-completion states.
4. Sanitize displayed rich content and keep source links constrained to approved evidence URLs. Never render arbitrary agent HTML.
5. Verify navigation away from dirty forms and clear drafts after session erasure.

### Backend work

1. Add configurable rate limits for session creation, calculation, mutation and message requests. Return Retry-After where applicable.
2. Enforce bounded body sizes, list limits, timeouts and database resource limits. Validate streaming body size before buffering a potentially unbounded request.
3. Add redacted structured logging with correlation IDs, durations and stable error codes. Do not log keys, credentials or raw messages by default.
4. Add scheduled retention cleanup, ownership tests, secret checks and tested backup/restore procedures for a persistent pilot.
5. Verify idempotency TTL, request coordination and revision checks with concurrent PostgreSQL connections and multiple workers.
6. Add CI checks for formatting, types, backend tests, schema drift, frontend tests and a production frontend build.

Deliverables: automated regression suite, accessibility review and operational checks.

Completion gate: critical application journeys pass browser tests; isolation and mutation races pass integration tests; no secret appears in the client bundle or routine logs; all known release-blocking defects are resolved.

## Stage 9 Deploy and hand over

Goal: deliver a reproducible hosted application with a rollback path.

### Frontend work

1. Build versioned production assets and configure correct caching for HTML versus hashed assets.
2. Verify route refresh, source links, empty states and forms on the deployed origin.
3. Add a visible application version and a support-friendly request ID on errors.

### Backend work

1. Create a multi-stage container that builds the frontend and runs the Python API as a non-root user.
2. Bind to 0.0.0.0 and the platform PORT. Route /api to the application and other valid frontend paths to the SPA fallback.
3. Configure external PostgreSQL, managed secrets, explicit origins, service permissions and readiness probes.
4. Apply migrations through a controlled job before traffic reaches the new revision. Use backward-compatible changes where rollback is required.
5. Configure model-independent health checks, limited concurrency and instance counts, monitoring and cost alerts. Chat readiness may be reported separately from core API readiness.
6. Deploy to a staging service, run smoke tests, then release the verified revision. Retain the prior compatible revision and test rollback.
7. Publish setup, environment configuration, migration, backup, erasure and incident-recovery instructions.

Deliverables: deployed URL, build identifier, runbook and release checklist.

Completion gate: data survives process restart and instance replacement; concurrent browser sessions remain isolated; failed chat does not break manual features; the team can restore the previous compatible revision and recover database data.

## Stage 10 Optional extensions after the core release

### Campus mode

Backend adds consented membership, group assignments, participation denominators, equivalent comparison windows and minimum-group suppression. Frontend adds a leaderboard explaining coverage and normalization. Do not rank groups by raw totals or expose individual activity logs. Release only when consent and privacy rules work end to end.

### Hindi and Telugu application support

Externalize UI strings, format dates and decimal displays through locale utilities and test layout expansion. Store canonical quantities, machine enums and source identifiers unchanged. Translate application errors through stable codes. Conversational language behavior remains outside this plan.

### Accounts and cross-device history

Add a managed identity integration and a carefully designed anonymous-session claim operation. Prevent account linking from revealing another anonymous user's history. Add account export, retention and deletion controls before promising persistent personal records.

### More factor regions

Add an explicit factor-review workflow with exact dataset rows, gas basis, boundaries and versioning. Frontend region selection exposes only approved supported capabilities. Historic receipts keep their original factors; do not silently recalculate past logs.

## Dependency order and suggested work split

Stage 0 is the shared prerequisite. Backend Stage 1 and frontend Stage 2 can then proceed concurrently using fixtures. Stage 3 is the first fully integrated slice. Stages 4 and 5 build on durable logging. Stage 6 follows summary correctness. Stage 7 can be designed earlier against mocks but must use the durable request and ledger infrastructure before release. Stages 8 and 9 close the core application. Stage 10 is optional.

| Workstream | Primary responsibilities | Handoff |
| --- | --- | --- |
| Frontend | Screens, forms, query state, accessibility, browser tests | Typed requests and evidence-based rendering |
| Backend | Domain services, repositories, API models, auth, concurrency and calculations | Frozen OpenAPI and real fixtures |
| Verification and deployment | Integration tests, CI, migrations, container and release checks | Reproducible acceptance report |
| Separate agent workstream | Model behavior and agent execution internals | Implements AgentGateway without changing application ownership rules |

These are responsibilities, not a requirement to add more team members. With two developers, assign one frontend owner and one backend owner and share release verification. A single developer should complete each end-to-end slice before starting another.

## Planning estimates

| Stage | Frontend effort | Backend effort | Milestone |
| --- | --- | --- | --- |
| 0 Contracts and screen map | 0.5 to 1 day | 0.5 to 1 day | Agreed application boundary |
| 1 Persistence | Fixture work overlaps | 1.5 to 3 days | Restart-safe ledger |
| 2 Shell and session | 1 to 2 days | 0.5 to 1.5 days | Usable application shell |
| 3 Logging | 1.5 to 2.5 days | 1 to 2 days | All categories work end to end |
| 4 Dashboard | 1 to 1.5 days | 0.5 to 1.5 days | Trustworthy totals and trends |
| 5 History and edits | 1 to 2 days | 1 to 2 days | Correctable durable history |
| 6 Insights | 0.5 to 1.5 days | 1 to 2 days | Grounded comparisons and savings |
| 7 Chat transport | 1 to 2 days | 1.5 to 3 days | Mock-ready durable chat integration |
| 8 Hardening | 1 to 2 days | 1 to 2 days | Release candidate |
| 9 Deployment | 0.5 to 1 day | 1 to 2 days | Hosted and recoverable application |

These are rough person-day estimates for focused implementation, excluding agent work, review delays and optional extensions. Frontend and backend columns represent effort rather than additive calendar duration because work can overlap. Re-estimate after Stage 0 and after the first durable integration. The full plan is a post-prototype roadmap and is larger than the event's three-hour build window.

## Three hour hackathon cut

If the immediate goal is only the hackathon demo, narrow the application plan: first freeze the current API and fixtures; then build one responsive page containing manual activity entry, calculation receipt, recent records and logged totals. Use the existing local backend and clearly disclose memory mode. Add source detail and one scenario card, verify the four-category flow and rehearse the demo. Keep the ADK development interface for conversation.

Defer accounts, durable request recovery, campus mode, multilingual UI and a public production deployment from that cut. Do not present a local in-memory demo as the completed full application.

## Required end to end acceptance scenarios

| Scenario | Expected result |
| --- | --- |
| New visitor starts a session | Valid scope and timezone are visible; server creates one session |
| Bus preview then save | Preview changes no total; save adds exactly one activity |
| Double-click or network retry | One commit and a recoverable receipt |
| AC hours without power | Form requests required inputs and creates no emissions estimate |
| Unsupported India grid | Explicit missing-factor state with no silent UK substitution |
| Food recipe selected | Ingredient masses and exclusions remain visible with the estimate |
| No logs on a date | UI distinguishes no recorded activity from measured zero |
| Record corrected | Revision increases and all affected totals refresh once |
| Concurrent stale edit | Conflict appears and the current record can be reloaded |
| Record deleted | Removed from active history and totals, with no fake undo |
| Missing or zero baseline | No fabricated percentage appears |
| Scenario generated | Alternative and saving are evidenced; actual totals remain unchanged |
| Agent unavailable | Manual entry, history and dashboard remain operational |
| Chat partially completes | Saved receipts remain visible and retries do not duplicate them |
| Service restarts | Durable session and history remain readable |
| Session erased | Credential is invalidated and stored session data is removed |
| Unauthorized record lookup | No activity or calculation evidence is disclosed |

## Release checklist

- All required screen states have been exercised against the actual API.
- OpenAPI, generated frontend types and the written contract agree.
- PostgreSQL migration, concurrency, expiry and erasure tests pass.
- Browser tests pass for manual logging, summaries, history and recovery.
- Source attribution and regional limits are visible in result details.
- Production build contains no provider credentials or sensitive configuration.
- Health checks, redacted logs, cleanup, backups and rollback are operational.
- Remaining limitations are documented and optional work is clearly separated.

## References

- Existing project baseline: ../README.md and ../carbon_coach/api.py.
- Product requirements: Carbon_Coach_PRD.md.
- Target API contract: Carbon_Coach_API_Contract.md.
- Original stack proposal: Carbon_Coach_Tech_Stack.md.
- Vite official guide: https://vite.dev/guide/
- TanStack Query official overview: https://tanstack.com/query/latest/docs/framework/react/overview
- Alembic official documentation: https://alembic.sqlalchemy.org/en/latest/
- FastAPI security documentation: https://fastapi.tiangolo.com/tutorial/security/
