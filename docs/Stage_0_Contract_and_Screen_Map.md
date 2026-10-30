# Stage 0 Application Contract and Screen Map

The implemented API schema is generated from named Pydantic request and response models in `carbon_coach/schemas.py`. `docs/openapi.json` and `frontend/src/api/schema.d.ts` describe the currently implemented version. The original API contract describes the larger target; differences below are explicit so frontend work does not assume unfinished behavior.

## API contract gap checklist

| Area | Implemented in Stage 0 | Planned next |
| --- | --- | --- |
| Typed contracts | All JSON success responses and shared error schema; typed activity dates | Additional fields follow their owning stage |
| Errors | Common envelope for validation, domain, routing and unexpected errors | Rate limits and durable request errors |
| Calculation detail | Owned immutable receipt retrieval with factor evidence | Durable storage and conversion evidence links |
| Activity detail | Owned active record plus calculation; revision supplied | Correction lineage and pagination |
| Session creation | Timezone validation and anonymous bearer token | Idempotent bootstrap, browser cookies and CSRF in Stage 2 |
| Session lifetime | Memory mode and 24 hour inactivity deadline | Durable retention and full cleanup in Stage 1 |
| Calculation requests | Four discriminated input variants; server selected approved factors | Explicit factor-version selection and conversion endpoint in Stage 3 |
| List filtering | Valid category and ISO date validation; exclusive end | Cursor pagination and bounded pages in Stage 5 |
| Totals | Logged totals, coverage and daily buckets | Category filter and richer metadata in Stage 4 |
| Comparisons | Not available | Previous-equivalent windows in Stage 6 |
| Reductions | Today or week, up to three supported scenarios | Constraints and custom periods in Stage 6 |
| Chat integration | AgentGateway protocol, real adapter and explicit mock | Structured pending items, durable requests and 202 recovery in Stage 7 |
| Locales | English only | Optional Hindi and Telugu application strings |
| Readiness | Process and registry probes | Database readiness in Stage 1 |

Current receipt fields intentionally differ from the original target: calculations retain full factor snapshots and disclose category boundaries through those snapshots; activities expose a `deleted` boolean instead of a deletion timestamp. Health probes are typed operational responses without the application envelope. These are frozen baseline decisions for this release, not undocumented frontend assumptions.

## Date and numeric decisions

- Activity date is an ISO local calendar date. Audit time is UTC.
- Date windows include start_date and exclude end_date. Weeks begin Monday in the session timezone.
- Explicit dates require period=custom; malformed filters and reversed ranges fail validation.
- A future timezone-setting feature preserves stored activity dates and changes only future relative-date resolution.
- Activity inputs accept up to six decimals. Stored emissions have six decimal places and displayed estimates two. Factor precision remains as published, including additional decimals created by tonne-to-kg conversion.
- Backend owns calculation, aggregation and savings. Frontend formats values without arithmetic.
- No records means unknown actual emissions, even when recorded total is zero.

## Screen map and response ownership

| Route | Screen | API fields used | Required states |
| --- | --- | --- | --- |
| /welcome | Session setup | session_id, expires_at, storage_mode, timezone, region | Creating, failure, returning, expired |
| /dashboard | Logged totals | summary display_total_kg_co2e, daily, by_category, logged_day_count, coverage_note | Loading, empty, populated, error, partial coverage |
| /log | Category forms | CalculationInput; calculation preview and factor_snapshots | Draft, invalid, calculating, preview, saving, saved, stale preview |
| /activities | History | items, revision, activity_date, next_cursor | Loading, no matches, filtered, conflict, mutation error |
| /activities/:id | Record detail | activity and calculation | Loading, not found, evidence, edit, delete confirmation |
| /insights | Alternatives | suggestions, baseline_kg_co2e, alternative_kg_co2e, saving_kg_co2e, overlap_group | Loading, unavailable, eligible, error |
| /chat | Application chat | MessageResponse status, reply, warnings, committed_activity_ids | Mock, sending, clarifying, partial failure, unavailable |
| /sources | Factor registry | Factor fields and recipes | Loading, source detail, unsupported region, unavailable version |
| /settings | Session controls | Existing session metadata and erase route | Current values, erasing, erased, failure; timezone editing deferred |

Comparisons, pagination controls, resumable requests and editable timezone must not be shown as functional until the corresponding stage ships. No custom frontend has been built at this stage; this screen map defines the next UI work.

## Frontend state ownership

Server responses belong in query state. Form drafts, open dialogs and navigation choices belong in component state or the URL. Mutation success invalidates activity, summary and reduction queries together. An unknown mutation outcome keeps the same idempotency key. Display expiry, unsupported-factor and network errors distinctly. Session erasure must clear every session-scoped query and draft.

## Agent integration boundary

`AgentGateway.run` receives an authorized session ID, request ID, message, locale and a copied ledger. It returns a status, safe reply, resulting ledger, newly committed activity IDs and warnings. `erase` removes adapter-owned session context. The application owns authorization, retries and persistence. The real adapter wraps existing ADK behavior without changing agent prompts, model selection or tools. MockGateway is explicitly labeled and changes no activities.

Development mode uses `GATEWAY_MODE=mock`. This enables frontend integration without provider calls and does not imply working agent inference. The new committed IDs field excludes records that existed before the turn.

## Verification

Run `python scripts/export_contract.py` to regenerate OpenAPI, frontend type definitions and deterministic empty, populated and error fixtures. Run it with `--check` to detect schema drift. Tests validate examples against response models, check ownership on evidence detail, cover malformed dates and route errors, and exercise mock chat without network calls. Existing agent-runner tests remain unchanged.
