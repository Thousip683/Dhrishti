# Carbon Coach API Contract

Version 1.0 | 30 October 2026 | Proposed application contract

## Purpose and implementation boundary

This document specifies the Carbon Coach application API and the Python tools exposed to the ADK agent. It is an implementation contract, not a description of an already running service. These routes belong to a proposed FastAPI facade; they are not native ADK endpoint guarantees. An ADK development UI may invoke the same service functions directly without exposing every route during the hackathon.

The contract supports session creation, chat, deterministic calculation, activity logging, summaries, reduction scenarios and factor evidence. Optional campus endpoints are outside v1. All examples use synthetic fixture factors, never production environmental evidence.

## Shared protocol rules

Base path is /api/v1 over HTTPS in deployment; localhost HTTP is allowed for development. Bodies and replies use application/json. All identifiers are opaque UUID strings. Examples use short readable IDs as placeholders. All documented fields are required unless labeled optional or nullable. Reject unknown input fields. Dates use YYYY-MM-DD; timestamps use RFC 3339 UTC. Timezones use IANA names, defaulting to Asia/Kolkata.

Quantities and emission values are decimal strings, not binary floating point values. Inputs accept plain decimal notation with at most six fractional digits, no exponent notation, NaN or infinity. API kg CO2e values have six fractional digits; display_kg_co2e has two. Use decimal half-up rounding. Sum stored values before display rounding. Counts, limits and revision numbers are JSON integers.

Each response includes request_id. Error responses follow the common error object below. Successful responses use status equal to success, except a chat may return needs_clarification or processing. Responses include no credentials except the one-time session-creation reply.

## Session credentials and authorization

POST /sessions is unauthenticated but rate-limited. It returns a random session credential once. Send it as Authorization: Bearer <session_token> on all session routes. Store only its hash on the server. Resource lookup must verify ownership before returning data; use 404 for an inaccessible resource and 401 for absent or invalid credentials. Do not trust session or user identifiers embedded in messages.

The demo has no cross-session account history. Restrict browser origins, enforce TLS outside localhost, avoid tokens in URLs, and do not log credentials. Session expiry defaults to 24 hours of inactivity. Expiry is extended by authorized activity. Erasure invalidates the credential immediately.

## Endpoint inventory

| Method and path | Result | Successful HTTP status |
| --- | --- | --- |
| GET /healthz | Process liveness without secrets | 200 |
| GET /readyz | Registry and storage readiness | 200 or 503 |
| POST /sessions | Create anonymous session | 201 |
| DELETE /sessions/{sid} | Erase session and owned data | 204 |
| POST /sessions/{sid}/messages | Run one conversational turn | 200 or 202 |
| GET /sessions/{sid}/requests/{rid} | Retrieve pending or completed turn | 200 |
| POST /sessions/{sid}/calculations | Calculate without logging | 201 |
| POST /sessions/{sid}/activities | Commit one calculation | 201 |
| GET /sessions/{sid}/activities | List active records | 200 |
| PATCH /sessions/{sid}/activities/{aid} | Replace calculation or date | 200 |
| DELETE /sessions/{sid}/activities/{aid} | Remove from future summaries | 204 |
| GET /sessions/{sid}/summary | Totals and trends | 200 |
| POST /sessions/{sid}/reductions | Compute hypothetical alternatives | 200 |
| GET /factors | Filtered public approved registry | 200 |
| GET /factors/{fid}/versions/{version} | Exact immutable factor evidence | 200 |

Session routes require a bearer credential. Factor endpoints and health checks are public and rate-limited. Session creation, messages, calculations, activity creation, patch and reductions require Idempotency-Key headers. Deletes are inherently idempotent; deleting an already deleted owned record returns 204 while the session is valid.

## Session schema

Create request fields are timezone, locale and optional region. Locale enum is en, hi or te; only en is required in MVP. Unsupported configured locales return 422. Region is a country or configured grid identifier and is not silently inferred from language.

```json
{
  "timezone": "Asia/Kolkata",
  "locale": "en",
  "region": "IN"
}
```

```json
{
  "request_id": "req-1",
  "status": "success",
  "session_id": "session-1",
  "session_token": "returned-once-secret",
  "expires_at": "2026-10-31T10:00:00Z",
  "storage_mode": "memory",
  "timezone": "Asia/Kolkata",
  "locale": "en",
  "region": "IN"
}
```

storage_mode is memory or database. The UI must warn about restart loss when it is memory. Deleting a session returns no body and removes messages, calculations, activity records, scenarios and stored idempotency responses subject to a documented operational backup policy in a production deployment.

## Calculation request

POST /sessions/{sid}/calculations accepts category, activity_date, input and optional factor_id plus factor_version. category discriminates travel, electricity, food or waste. The server chooses only approved compatible factors. An explicit factor must include its version and pass the same compatibility checks. Calculations are session-owned immutable records. An actual activity is not created by this endpoint.

| Category | Input fields | Validation |
| --- | --- | --- |
| travel | mode, distance_km, optional occupancy | mode in bus, car_petrol, car_diesel, motorcycle, bicycle, walking; distance 0 to 10000; occupancy positive integer when vehicle-km allocation is needed |
| electricity | kwh, grid_region | kwh 0 to 10000; region supported by registry |
| food | meal_type, servings | registered recipe ID; servings greater than 0 and at most 100 |
| waste | material, mass_kg, disposal_route | mass 0 to 1000; material and route must exist as a supported registry pair |

Waste material examples are food, paper, plastic and mixed; route examples are landfill, compost and recycling. These are candidate enums; only registry-backed pairs are accepted. A recipe defines ingredient amounts and factor references. Unknown meal_type returns supported recipe IDs. A serving count without a recipe is insufficient.

Travel occupancy must be absent for passenger-km factors, or match an explicit documented non-applicable policy; this contract rejects it to prevent double division. For walking and bicycle, a zero operational factor needs the same source and boundary metadata as any other factor. Activity date may be omitted for hypothetical calculations; actual logging requires a date no later than today in the session timezone.

```json
{
  "category": "travel",
  "activity_date": "2026-10-30",
  "input": {"mode": "bus", "distance_km": "12"},
  "factor_id": "fixture_bus",
  "factor_version": "test-v1"
}
```

```json
{
  "request_id": "req-2",
  "status": "success",
  "calculation": {
    "id": "calc-1",
    "category": "travel",
    "activity_date": "2026-10-30",
    "input": {"mode": "bus", "distance_km": "12"},
    "normalized_quantity": "12.000000",
    "normalized_unit": "passenger_km",
    "kg_co2e": "1.200000",
    "display_kg_co2e": "1.20",
    "formula": "12 * 0.10",
    "factor_refs": [{"id": "fixture_bus", "version": "test-v1"}],
    "gas_basis": "CO2e",
    "boundary": "fixture_operational",
    "assumptions": ["Synthetic test factor only"],
    "warnings": ["Not valid for environmental reporting"],
    "claim_ids": ["claim-calc-1-total"],
    "created_at": "2026-10-30T10:01:00Z"
  }
}
```

The fixture factor above exists only in test mode. Production requests naming fixture factors return FACTOR_NOT_AVAILABLE. kg_co2e applies only to CO2e-compatible factors; v1 rejects a CO2-only factor for this schema with INCOMPATIBLE_GAS_BASIS. Adding a CO2-specific result requires a versioned schema extension.

## Appliance conversion tool

The tool convert_appliance_energy(power_kw, hours, duty_cycle) returns kwh, formula and assumptions. duty_cycle is optional only when power_kw is explicitly average input power; otherwise ask for duty cycle or measured energy. hours must be between 0 and 24 per daily entry, duty_cycle greater than 0 and at most 1. For 1.5 kW average power and 4 hours, output is 6 kWh. The resulting kWh then enters calculate_electricity_emissions. Do not treat cooling capacity or energy-efficiency star rating as input power.

No separate public endpoint is required in v1; the conversational orchestrator uses this Python tool and includes its evidence in the calculation. The electricity endpoint accepts kWh only.

## Activity commit and mutation

POST /activities takes calculation_id, activity_date and optional note of at most 500 characters. The server copies calculated values and factor references from its own record; it never accepts a caller-supplied emissions total. Calculation ownership is checked. One calculation can be committed once; a second commit returns 409 CALCULATION_ALREADY_LOGGED, unless it is a replay with the same idempotency key.

```json
{"calculation_id":"calc-1","activity_date":"2026-10-30","note":"Morning commute"}
```

The 201 response contains request_id, status and activity. Activity fields are id, calculation_id, category, activity_date, kg_co2e, factor_refs, note, revision, created_at, updated_at and deleted_at. Initial revision is 1 and deleted_at is null. Raw calculation data remains accessible through the receipt returned with chat or an activity detail expansion in the list endpoint.

PATCH requires If-Match with the current quoted revision and a new calculation_id and/or activity_date and optional note. At least one field must change. A replacement calculation must belong to the same session and be uncommitted. Mutation is atomic, marks the old calculation superseded and increments revision. Stale revision returns 412 REVISION_MISMATCH. DELETE requires If-Match for an active record, soft-deletes it and excludes it from all future totals. Full session erasure physically removes its data in the primary store.

GET /activities accepts start_date inclusive, end_date exclusive, category, limit from 1 to 100 default 25, and optional opaque cursor. Sort by activity_date then created_at then id, ascending. Return items and next_cursor nullable. The cursor is bound to the filter and a snapshot revision to avoid duplicates during pagination. Invalid or stale cursor returns 409 CURSOR_EXPIRED. No deleted records are returned.

## Conversation request and response

POST /messages accepts text of 1 to 4000 characters and optional locale. The service serializes turns within a session. A simultaneous unresolved turn returns 409 SESSION_BUSY. Model-visible context treats user text as untrusted instructions regarding tools and evidence.

```json
{"text":"I travelled 12 km by bus today and used the AC for 4 hours."}
```

```json
{
  "request_id":"req-3",
  "status":"needs_clarification",
  "message_id":"msg-1",
  "reply":"Your bus journey is saved. What was the AC energy use in kWh, or its average input power in kW?",
  "committed_activity_ids":["activity-1"],
  "calculation_ids":["calc-1"],
  "pending_items":[{"id":"pending-1","category":"electricity","missing_fields":["kwh_or_power"],"provided":{"hours":"4"}}],
  "claims":[{"id":"claim-calc-1-total","kind":"emissions","value":"1.200000","unit":"kg_CO2e","evidence_id":"calc-1"}],
  "warnings":["Fixture response shown for contract testing only"]
}
```

reply is localized text. claims is the authoritative list of derived numerical values that may appear in that text. kind includes emissions, total, difference, percent_change, saving and energy_conversion. Each has a tool-generated evidence_id. Quantities supplied by the user are separately identifiable as input, not independently asserted environmental facts.

A turn may partially succeed: completed activities are committed exactly once, pending_items retain unresolved inputs and status is needs_clarification. Never claim rollback of entries already returned as committed. If the model fails after writes, return the stored receipts and a safe deterministic response. A 30-second deadline returns 202 processing with request_id and retry_after_seconds; GET /requests/{rid} returns processing or the stored final response. Only one request with the same idempotency key executes.

## Summary contract

GET /summary accepts period equal to today, week or custom; default week. custom requires start_date inclusive and end_date exclusive, limited to 366 days. Do not send explicit dates with today or week. Optional comparison is none or previous_equivalent; default none. category is optional. The server resolves dates, never the LLM.

Return request_id, status and summary with period, timezone, start_date, end_date, as_of, total_kg_co2e, display_total_kg_co2e, by_category, daily, activity_count, logged_day_count, window_day_count, coverage_note, factor_versions, comparison and claim_ids. by_category contains all four categories with decimal totals. daily contains local date, recorded_kg_co2e, activity_count and has_records. comparison is nullable and, when present, has baseline dates, baseline_total, absolute_change, percent_change nullable and comparability_warnings.

An empty session returns 200, recorded total zero, activity_count zero and “No activities logged in this window.” That is not a claim of zero real emissions. Prior zero totals produce null percent_change and reason ZERO_BASELINE. Missing comparable records produce unavailable comparison and reason INSUFFICIENT_DATA. Different factor versions are disclosed; v1 does not silently recalculate history. A week is Monday through next Monday in the session timezone. Partial-week comparison uses the same elapsed local-day coverage and marks the current day partial.

## Reduction scenarios

POST /reductions accepts period using the summary semantics, optional start_date and end_date for custom periods, max_suggestions from 1 to 3 default 3, and optional constraints. constraints may include excluded_modes and dietary_preferences. Return suggestions plus unavailable_reason nullable. With no eligible records, return an empty suggestions list and NO_ELIGIBLE_ACTIVITIES rather than a fabricated saving.

Each suggestion contains id, baseline_activity_ids, action, baseline_kg_co2e, alternative_kg_co2e, saving_kg_co2e, period, assumptions, factor_refs, evidence_id, overlap_group and claim_ids. Saving equals max(0, baseline minus alternative). Recalculate the same activity quantity with a compatible alternative factor. Exclude nonpositive savings. Do not combine alternatives sharing overlap_group. Do not infer monthly frequency from one entry. Scenarios never mutate actual totals.

For a test fixture car factor of 0.20 and bus factor of 0.10 per passenger-km, replacing a 12 km car journey yields baseline 2.40, alternative 1.20 and saving 1.20 kg CO2e. These figures are synthetic test expectations only.

## Factor evidence schema

GET /factors supports category, region, approved_only fixed true in production, limit and cursor. A Factor has id, version, category, activity_key, value, denominator_unit, gas_basis, boundary, geography, reference_year, source_publisher, source_title, source_url, source_locator, retrieved_at, methodology, limitations, approved and fixture_only. Value is a decimal string. Source locator identifies the exact table, worksheet or row; a landing page alone is insufficient for numeric provenance.

Records are immutable by ID and version. Updating factors creates a new version and registry release. Existing calculation receipts retain the original factor snapshots. API clients cannot upload or edit factors. A recipe has ingredient masses and factor references; its composite factor includes the recipe version and serving definition.

## Error schema and status mapping

```json
{
  "request_id":"req-error",
  "status":"error",
  "error":{
    "code":"MISSING_INPUT",
    "message":"Provide measured kWh or appliance power and duration.",
    "retryable":false,
    "field_errors":[{"field":"input.kwh","reason":"required"}]
  }
}
```

| HTTP | Codes and meaning |
| --- | --- |
| 400 | INVALID_JSON or INVALID_REQUEST for malformed structure |
| 401 | UNAUTHORIZED for absent, invalid or expired credential |
| 404 | NOT_FOUND for missing or inaccessible resources |
| 409 | IDEMPOTENCY_CONFLICT, SESSION_BUSY, CALCULATION_ALREADY_LOGGED, CURSOR_EXPIRED |
| 412 | REVISION_MISMATCH |
| 413 | PAYLOAD_TOO_LARGE |
| 422 | MISSING_INPUT, INVALID_QUANTITY, UNSUPPORTED_ACTIVITY, FACTOR_NOT_AVAILABLE, INCOMPATIBLE_GAS_BASIS, INCOMPATIBLE_BOUNDARY, INVALID_DATE |
| 429 | RATE_LIMITED with Retry-After header |
| 502 | MODEL_UNAVAILABLE or invalid upstream reply |
| 503 | STORAGE_UNAVAILABLE or REGISTRY_UNAVAILABLE |

Human clarification is a successful chat status, not HTTP 422. Direct calculation validation uses 422. Never include stack traces, secrets or provider payloads in user-facing errors.

## Idempotency and concurrency

Keys are caller-generated UUIDs scoped to session plus method and path. Session creation keys are scoped to a short-lived anonymous client nonce. Store the canonical payload hash and completed response for 24 hours or until session erasure. Repeating the same key and payload returns the same resource and result; a different payload returns 409. An in-flight replay returns 202 with the same request ID. A model retry uses deterministic child mutation keys derived from request ID and candidate index.

Use a database transaction for activity writes, idempotency records and revision updates. Memory mode uses a per-session lock. Summaries read a consistent snapshot. Cross-instance Cloud Run operation requires a database lock or durable coordination; an in-process lock alone is insufficient.

## ADK Python tool contract

| Tool | Inputs | Output and behavior |
| --- | --- | --- |
| calculate_travel_emissions | mode, km, optional occupancy | Calculation receipt; no write to activity log |
| convert_appliance_energy | power_kw, hours, optional duty_cycle | Energy conversion evidence |
| calculate_electricity_emissions | kwh, grid_region | Calculation receipt |
| calculate_food_emissions | meal_type, servings | Recipe-backed receipt |
| calculate_waste_emissions | material, mass_kg, disposal_route | Calculation receipt |
| log_activity | calculation_id, activity_date, optional note | Activity receipt; trusted session comes from ToolContext |
| get_summary | period, optional dates and comparison | Summary evidence |
| suggest_reductions | period, optional constraints | Scenario evidence |
| correct_activity | activity_id, revision, replacement calculation | Atomic correction receipt |
| delete_activity | activity_id, revision | Deletion receipt |

Tools use the same domain service as REST. ToolContext supplies session ownership and request identity; the model cannot select an arbitrary session credential. Return a structured success or error object. Tool exceptions are normalized. Calculations, summaries and savings must not be reimplemented in prompts or frontend code.

## Contract verification checklist

Test exact fixture arithmetic, unit conversion, passenger versus vehicle allocation, missing inputs, unsupported registry pairs, negative or nonfinite inputs, future log dates, rounding after aggregation, date boundaries and empty records. Verify idempotent retries, stale revisions, session isolation, expiry, partial chat completion and storage failure. Confirm the deployed routes agree with generated OpenAPI and examples. Compare every displayed numerical claim with a tool evidence record. Pin this v1 contract before frontend integration; breaking changes use a new API version.

## References

- Product requirements: Carbon_Coach_PRD.md.
- Architecture and dependency decisions: Carbon_Coach_Tech_Stack.md.
- Google ADK: https://adk.dev/
- Gemini API: https://ai.google.dev/gemini-api/docs
- Cloud Run container contract: https://docs.cloud.google.com/run/docs/container-contract
