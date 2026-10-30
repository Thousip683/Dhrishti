# Carbon Coach Product Requirements Document

Version 1.0 | 30 October 2026 | DevFest 2026 hackathon

## Product purpose

Carbon Coach is a conversational AI agent that helps students and households estimate emissions from daily travel, electricity, food and waste. It uses Google ADK and a Gemini model to interpret requests, while deterministic Python tools calculate every emissions figure, total, comparison and potential saving. This document defines the product to build, its acceptance criteria and the three-hour delivery plan.

This is a proposed implementation specification. Requirements marked P0 form the hackathon MVP; P1 and P2 are extensions. The system estimates the footprint of logged activities, not a complete audited personal carbon footprint.

## Problem and intended outcome

People describe activities naturally but rarely know the corresponding emissions or which changes matter most. Existing information uses different units, regional assumptions and lifecycle boundaries. Carbon Coach should make an estimate understandable and traceable, remember the user's logs and suggest feasible changes with calculated savings.

The primary outcome is a working demonstration of conversational input, real tool execution, session memory and useful recommendations. The agent must acknowledge uncertainty and ask for missing information rather than invent quantities or factors.

## Users and needs

| User | Main need | Successful interaction |
| --- | --- | --- |
| Student | Understand commute and hostel electricity | Log a bus journey and compare an alternative |
| Household member | Track daily activities | See category totals over selected dates |
| Campus participant | Understand group performance | Compare consented, normalized group data in a future extension |
| Judge or evaluator | Verify the agent actually calculates | Inspect tool evidence and reproduce a result |

Students are the primary MVP audience. Household support uses the same activity model; shared household allocation must be explicit. Campus aggregation is optional and does not block the personal experience.

## Goals and success measures

| Goal | Proposed acceptance target |
| --- | --- |
| Ground numerical claims | All emissions, totals, percentages and savings reference tool evidence |
| Cover the challenge | Supported examples for all four categories |
| Preserve memory | Repeated summaries include all active logs within one session |
| Calculate reliably | All deterministic calculation and boundary tests pass |
| Handle uncertainty | Missing essential inputs produce a clarification and no invented estimate |
| Provide useful coaching | At least one eligible logged activity produces a sourced, quantified alternative |
| Be demo ready | Complete the scripted flow within the three-minute presentation |
| Remain responsive | Target p95 conversational latency below 15 seconds in a small measured demo run; report actual results |

These are release targets, not measured performance claims. A numerical-grounding check validates structured claims before display; prompt instructions alone are insufficient.

## Scope and priorities

### P0 must ship

- English text conversation through a lightweight web chat or ADK development interface.
- Google ADK agent using Gemini with Python tools.
- Calculation support for travel distance, electricity consumption, configured meal recipes and waste mass plus disposal route.
- Source and factor version attached to every estimate.
- Clarification when mode, amount, unit, meal definition or waste route is missing.
- Session activity log, date-filtered totals, category breakdown and daily trend.
- Personalized reduction scenarios using the same calculation engine.
- Session isolation, input validation and predictable error messages.
- Golden evaluation cases, deterministic tests and a reproducible demo.

### P1 if time allows

- Custom FastAPI interface implementing the accompanying API contract.
- Cloud Run deployment with durable storage and a shareable URL.
- Activity correction, deletion and full-session erasure through the UI.
- Hindi and Telugu text, with unchanged canonical tool values and calculations.
- Prior-period comparisons when the logged coverage is adequate.

### P2 extensions

- Separate Tracker and Coach agents with one authoritative logging service.
- Campus leaderboard with membership verification, consent and privacy thresholds.
- User accounts, cross-device history, exports and configurable goals.

Excluded from the MVP are carbon credit purchases, certified accounting, automatic utility or bank imports, GPS surveillance, voice capture and claims of verified offsets. The agent must not imply it measures unlogged activities.

## Core journeys

### Log travel and electricity

The user says, “I travelled 12 km by bus today and used the AC for 4 hours.” The agent recognizes two activities. It can calculate the bus estimate if a suitable bus factor exists. For AC it asks for measured kWh or rated power and usage assumptions. Four hours alone is not electricity consumption. If the user supplies 1.5 kW average input power, the conversion tool returns 6 kWh before the electricity tool estimates emissions. A rated maximum is labeled an approximation when used as average power.

Completed activities are logged independently and acknowledged. Incomplete activities remain pending and do not enter totals. The reply distinguishes saved entries from pending clarification. A question such as “What would 12 km by bus emit?” calculates without logging; “I travelled” or “log this” expresses logging intent.

### Inspect memory

The user asks, “How did I do this week?” The summary tool resolves the local calendar week in the session timezone, returns logged totals, daily buckets, category totals and coverage. The agent says “your logged emissions” and shows which dates have records. No-record dates are unknown, even if the chart uses zero recorded emissions for those dates.

### Get a practical recommendation

The user asks how to reduce their footprint. The recommendation tool identifies an eligible activity and recalculates a specific alternative. The response names the original and replacement assumptions, estimated kg CO2e saving and period. A hypothetical saving does not subtract from the actual log. Overlapping alternatives are not added together.

### Correct a mistake

The user says the journey was 8 km rather than 12 km. The agent identifies the target record or asks which one, recalculates and replaces it with an audit link. Retrying a request must not add a second copy. A minimum fallback is a clear correction workflow through the service even when no custom editing UI ships.

## Functional requirements and acceptance criteria

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| FR01 | Interpret multiple activities | Mixed travel and electricity input yields separate validated candidates |
| FR02 | Clarify incomplete input | AC hours without power or kWh produces a question and no electricity estimate |
| FR03 | Calculate using tools | A spy or trace proves the relevant tool ran before a numerical reply |
| FR04 | Record provenance | Each calculation exposes factor ID, version, units, source and assumptions |
| FR05 | Log actual activities | A successful log references a server-created calculation and activity date |
| FR06 | Avoid unwanted writes | Hypothetical calculation requests create no activity record |
| FR07 | Summarize memory | Totals equal the sum of active matching records, with date and category filters |
| FR08 | Produce trends | Daily buckets use local dates and include logged coverage metadata |
| FR09 | Compare appropriately | Missing baseline or zero denominator returns unavailable rather than a fabricated percentage |
| FR10 | Suggest reductions | Each saving is baseline minus alternative using compatible boundaries and factors |
| FR11 | Correct and remove logs | Replacement or deletion changes subsequent totals once and preserves mutation consistency |
| FR12 | Handle unsupported activities | Return supported choices or request details; never silently substitute a factor |
| FR13 | Isolate sessions | A credential for one session cannot read or mutate another |
| FR14 | Explain estimates | Responses label modeled values as estimates and expose assumptions |

## Calculation and evidence policy

Emissions equal normalized activity quantity multiplied by an approved factor. Use decimal arithmetic internally; retain six decimal places in stored kg CO2e and round display values to two decimal places using half-up rounding. Sum stored values before display rounding. Unit conversions are deterministic and included in evidence.

Travel distinguishes vehicle-km from passenger-km. Divide a vehicle-km factor by explicit occupancy once; do not divide passenger-km factors again. “Bike” requires clarification between bicycle and motorcycle. Bicycle operational emissions may be zero under a documented operational-only boundary; do not call this a zero lifecycle footprint.

Electricity uses kWh and an explicitly selected geography and reporting year. Food estimates use named meal recipes with ingredient masses; a generic meal label requires a documented serving definition. Waste uses material, mass and treatment route. Avoid adding a food-production estimate a second time as waste-production emissions. Recycling credits and negative factors are disabled in the MVP.

The factor registry records source URL, publisher, dataset and version, source row or table, geography, year, unit, gas basis, lifecycle boundary, value and limitations. Dataset landing pages identify candidate sources; actual numeric values must be checked against the selected dataset before release. A CO2-only electricity factor must remain labeled CO2 and must not silently become an all-gas CO2e factor. Unsupported or incompatible factors are rejected or disclosed outside a combined total.

No real emission factors are prescribed by this PRD. API examples use explicitly synthetic test factors and must never become the production registry by accident. For India, inspect the CEA dataset and its gas scope. For travel and waste, assess the UK government conversion-factor dataset and clearly disclose geographic applicability. Food requires ingredient-based research data with consistent boundaries.

## Comparison and coaching rules

Prefer comparisons against the user's own logged prior period. Calendar “this week” runs Monday 00:00 to the following Monday 00:00 in the session timezone. A partial week compares the equivalent elapsed window of the previous week. Show absolute difference; return percentage only when the baseline is positive. Disclose incomplete coverage and factor-version changes.

Do not introduce a national average unless a sourced, compatible benchmark is configured. A campus leaderboard must normalize by a disclosed denominator such as participant-days and suppress groups below a proposed minimum of five consented participants. Compare equivalent periods and categories; raw group totals alone are misleading.

Recommendations respect feasible travel modes, dietary preferences and user constraints. Do not infer a recurring habit from a single log. Monthly or annual extrapolation requires an explicit frequency and is labeled a scenario. Savings are estimates, not verified reductions. Group mutually exclusive suggestions using an overlap identifier.

## Experience and content requirements

Replies lead with the result or next question, then provide the most relevant assumption and a source link. Prefer a short activity receipt, a visible saved state, a category breakdown and one to three useful suggestions. Loading and error states must be understandable. Support keyboard navigation, labeled inputs and text equivalents for charts. Language extensions translate prose while retaining machine enums and decimal semantics.

Avoid shaming, moral scores and unsupported claims of being “green.” All displayed numerical claims derived by the agent must have a tool-returned claim identifier. If generated prose adds an unsupported number, replace that response with a deterministic template assembled from the tool result.

## Data and privacy

Minimum records are Session, Calculation, Activity, Factor and ReductionScenario. Identity derives from the server-issued session credential, never a user ID supplied in a prompt. Default timezone is Asia/Kolkata and must be visible and changeable. Activity dates are local calendar dates; audit timestamps are UTC.

The local hackathon version may use in-memory session state and must disclose that a restart loses data. Cloud deployment uses durable storage; local files on Cloud Run are not treated as durable. Proposed anonymous retention is 24 hours of inactivity, enforced by cleanup. Provide session erasure. Store no names, exact routes or sensitive personal data unless needed and explicitly supplied. Keep API keys server-side and exclude prompts and credentials from routine logs.

## Quality and operational requirements

Validate finite nonnegative quantities, supported enums, units, dates and maximum payload sizes. Suggested technical caps are 10,000 km per travel entry, 10,000 kWh per electricity entry, 100 servings per food entry and 1,000 kg per waste entry; they are abuse limits, not claims about normal behavior. Future activity dates are rejected for actual logging; scenario calculations remain possible.

Serialize mutations within a session and use idempotency keys. On model failure, preserve completed writes and return their receipts; retries must not repeat them. Factors load from a versioned local registry, so calculation does not require live browsing. Tool or source failures must not trigger guessed values. Proposed service timeout is 30 seconds with a resumable request status.

## Evaluation and release gates

Use deterministic tests for arithmetic, rounding, conversions, occupancy, invalid values, period boundaries, idempotency, isolation and scenario savings. Golden conversations cover four categories, mixed input, AC clarification, unsupported mode, session recall, corrections, Hindi or Telugu if enabled and numerical prompt injection. Tool trajectory checks complement answer checks; a fluent final answer alone does not prove tool use.

Use synthetic fixtures for exact arithmetic: a bus test factor of 0.10 kg CO2e per passenger-km gives 1.20 kg for 12 km; an electricity test factor of 0.50 gives 3.00 kg for 6 kWh; the combined recorded total is 4.20 kg. These are test values only. Never present them as measured environmental factors.

Release when all P0 journeys work, every displayed emissions claim is traceable, all deterministic tests pass, secrets are absent from source, and the three-minute demo runs from a clean session. Report actual evaluation pass counts and measured latency rather than invented scores.

## Three hour implementation plan

| Time | Deliverable |
| --- | --- |
| 0 to 20 minutes | Confirm scope, select Gemini access, curate a small sourced factor registry |
| 20 to 60 minutes | Build models, calculation tools and deterministic tests |
| 60 to 100 minutes | Add ADK agent, logging, summaries and clarification behavior |
| 100 to 130 minutes | Add reduction scenarios and a usable chat interface |
| 130 to 155 minutes | Run golden cases and fix numerical grounding failures |
| 155 to 180 minutes | Rehearse demo; deploy only if core behavior is stable |

For a team of two, combine agent and interface work under one person and calculation plus evaluation under the other. For three or four people, separate interface, agent, calculation and verification responsibilities. Team size and three-minute demo duration follow the supplied proposed event format.

## Demo and judging alignment

Start with the mixed bus and AC example, show the AC clarification, log the clarified value, request a weekly summary and then a quantified alternative. Open the factor evidence or tool trace to prove the arithmetic. Finish with one golden case and the deployed URL if available.

Working tool use maps to 30 percent of judging, accuracy to 20 percent, suggestions to 20 percent, experience to 15 percent and deployment plus evaluation to 15 percent. Core calculation and evidence take precedence over optional bonuses.

## Risks and decisions before coding

The biggest risks are mismatched factor boundaries, ambiguous meal portions, session loss, duplicate writes and model-generated numbers. Mitigations are a reviewed registry, explicit servings, declared persistence mode, idempotency and deterministic claim rendering. Before implementation, choose the exact factor rows, Gemini model ID available to the team, persistence mode and interface. These are configuration decisions, not reasons to postpone building the deterministic core.

## Sources and related documents

- User supplied DevFest 2026 Carbon Coach problem statement is the product authority.
- Google ADK documentation: https://adk.dev/
- Gemini model catalog: https://ai.google.dev/gemini-api/docs/models
- UK government conversion factor collection: https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting
- CEA CO2 baseline database reports: https://www.cea.nic.in/cdm-co2-baseline-view?heading=CDM-CO%E2%82%82+Baseline+Database+Reports&lang=en&mappingId=234
- Food research dataset access: https://ourworldindata.org/grapher/ghg-per-kg-poore
- Related specifications: Carbon_Coach_API_Contract.md and Carbon_Coach_Tech_Stack.md.
