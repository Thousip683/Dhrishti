# Stage 3 Activity Logging

Stage 3 adds complete manual logging for travel, electricity, food and waste. Users enter details, preview a server calculation, inspect its sources and explicitly save it. Agent prompts, model settings and tools were not changed.

## User flows

Travel offers approved bus, petrol-car and diesel-car choices. Car entries require occupancy including the driver. Bus factors already use passenger distance, so stale car occupancy is omitted from bus requests. Electricity offers measured kWh or appliance input power plus duration, with an explicitly selected supported grid. Only the UK reference grid is currently configured.

Appliances distinguish average electrical input from rated input. Rated input requires an explicit duty cycle; average input is already time-averaged. Cooling capacity is not accepted as electrical input. Hours alone never produce an estimate.

Food uses the defined recipes returned by the backend, shows raw ingredient mass per serving, excludes cooking, oil and seasonings, and asks users to agree to those assumptions. Waste exposes only approved material and treatment combinations. All forms show the local activity date and allow an optional bounded note.

The preview is not a saved activity. It includes the tool-produced estimate, formula, factor snapshots, source locations, assumptions and limitations. Changing details immediately removes the prior save action. Editing and category changes are blocked while a request is running. After an acknowledged save, fields stay locked until the user explicitly starts another entry or chooses another category.

## Added API behavior

| Endpoint or input | Behavior |
| --- | --- |
| GET /api/v1/sessions/{sid}/capabilities | Returns supported travel choices, grids, recipes, waste routes, technical limits, timezone, server-local date and regional notice |
| POST /api/v1/sessions/{sid}/energy-conversions | Creates immutable session-owned conversion evidence using power_kw, hours, power_basis and optional duty_cycle; requires an idempotency key |
| GET /api/v1/sessions/{sid}/energy-conversions/{cid} | Retrieves conversion evidence after checking session ownership |
| Electricity input conversion_id | Links the electricity receipt to its conversion; the server rejects a foreign/missing ID or a kWh value different from the recorded conversion |
| Calculation factor_id and factor_version | Optional pair; rejects mismatched, incomplete, stale or incompatible references instead of substituting another version |

Calculation receipts now carry normalized_unit, formula, optional recipe_version and optional energy_conversion. Older receipts remain valid because these fields are optional. Food recipes use carbon-recipes-v1. Factor precision and original dataset versions are retained.

Appliance conversion multiplies validated electrical input, duration and an explicit duty-cycle assumption using Decimal. Rated input without duty cycle is rejected. Average input with a non-unit duty cycle is rejected to prevent applying the same adjustment twice. Inputs have technical limits and finite decimal validation. Conversion evidence is stored in the durable session context and copied into the resulting calculation receipt; no new SQL migration is required.

## Drafts and retry safety

Activity drafts are scoped to the session and stored in sessionStorage without credentials. Preview and conversion operations retain their original request keys across retries. Restored previews are fetched from the owned server calculation endpoint; the UI does not recompute them from local data.

Before saving, the client freezes calculation_id, activity_date, note and a save idempotency key. A network error or server failure leaves this operation pending and locks the form. After refresh, the user can retry the identical operation. If the first request committed but its response was lost, the server returns its original receipt and creates no duplicate. A known validation rejection unlocks the form for correction. Session erasure or expiry clears drafts, and late callbacks cannot recreate drafts for an invalidated session.

Successful saves invalidate the activity, summary and reduction queries. Navigating away during a pending save still leaves a recoverable operation; completion also invalidates those queries even if the logging component has unmounted.

## Validation

Frontend validation provides accessible field errors for required choices, decimal precision, technical ranges, occupancy, recipe confirmation and date constraints. Server validation remains authoritative. Source choices come from backend capabilities; unsupported India electricity factors and unsupported waste routes are never silently substituted.

Recorded activity dates cannot be in the future in the session timezone. The client uses the server-provided local date for defaults and upper bounds. Previewing, converting energy and suggesting alternatives do not add to actual totals. A zero recorded quantity is permitted where the domain allows it; a meal must have a positive serving count.

## Verification results

- 48 backend tests pass in the standard isolated run.
- 57 backend tests pass with SQLite and PostgreSQL storage variants enabled, including conversion evidence retrieved after repository restart.
- 15 frontend unit tests pass, including stale-preview clearing and restoring the exact pending save key.
- 14 real-browser tests pass across desktop and mobile. Tests log all four categories, verify overview/history updates, simulate a committed save with a lost response, reject incomplete appliances and future dates, and restore source evidence after refresh.
- TypeScript and Vite production build pass; generated OpenAPI/types/fixtures have no drift. Desktop and mobile calculation-preview screenshots were reviewed.

The application runs at http://127.0.0.1:8001/log. Full period-selection dashboards, filtered history with editing, comparisons and integrated agent chat remain in their planned later stages. Current factors remain UK references and global food averages rather than India-specific estimates.
