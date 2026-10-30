# Stage 2 Browser Session API

This extends the bearer-token API for the same-origin React application. It does not change agent prompts, tools or model behavior. The full machine-readable contract is in openapi.json and the generated frontend type definitions.

## Browser endpoints

| Endpoint | Request | Result |
| --- | --- | --- |
| GET /api/v1/browser/bootstrap | No body | Sets an HttpOnly bootstrap cookie and returns a CSRF token |
| POST /api/v1/browser/session | SessionInput plus Origin, X-CSRF-Token and Idempotency-Key | Creates or replays the browser session; sets the HttpOnly session cookie; returns public session metadata |
| GET /api/v1/browser/session | Session cookie | Restores metadata, CSRF token and expiry; returns 401 or 404 for unavailable credentials |
| PATCH /api/v1/browser/session | timezone plus Origin, X-CSRF-Token and Idempotency-Key | Updates timezone without changing stored local activity dates |
| DELETE /api/v1/browser/session | Session cookie plus Origin and X-CSRF-Token | Erases the primary-store session and dependent data; clears both cookies |

The response metadata contains session_id, expires_at, storage_mode, timezone, locale, region, csrf_token and chat_mode. chat_mode is mock, configured or unavailable. Configured means a provider key is present, not that provider availability has been verified. No browser response contains a bearer token or provider key.

## Authentication and CSRF

Browser credentials are opaque random values in HttpOnly SameSite Lax cookies. Secure is enforced on HTTPS and on non-local hosts. COOKIE_SECURE=true explicitly enables it for deployment. Session cookies are scoped to /api/v1; bootstrap cookies to /api/v1/browser. Their server records contain hashes, not plaintext credentials. The CSRF token is cryptographically derived from the browser credential and is exposed only through the same-origin API response.

Cookie-authenticated POST, PATCH and DELETE requests require an explicit allowed Origin and a matching X-CSRF-Token. Cross-site Fetch Metadata is rejected. SameSite is an additional control, not the only CSRF defense. Missing or invalid CSRF returns 403. Bearer-authenticated direct API requests continue to work without browser CSRF headers.

Configure ALLOWED_ORIGINS as an explicit comma-separated list. Never allow a wildcard with credentials. The Vite development proxy forwards /api to the local Python server while preserving the browser origin. Production serves the built frontend and API from the same service.

## Retry-safe browser creation

The bootstrap nonce scopes browser creation. Only its hash, the original settings fingerprint, session reference and expiry are persisted in browser_bootstraps. Retrying the same settings returns the same session even if the original response was lost before its session cookie reached the browser. Different settings against the same committed bootstrap return IDEMPOTENCY_CONFLICT. PostgreSQL uses an advisory transaction lock during bootstrap; SQLite serializes the transaction. Retry SESSION_BUSY using the original request key.

The frontend keeps a nonsensitive creation retry key and form drafts in sessionStorage. It never stores a session credential in localStorage or sessionStorage. The raw POST /api/v1/sessions endpoint remains available for direct bearer clients; its separate idempotent-bootstrap extension is not implemented by this browser-only flow.

## Expiry and erasure

The backend retains its 24 hour inactivity deadline. Successful cookie-authenticated requests renew the credential cookie and send X-Session-Expires-At. The frontend updates its expiry timer from that header, restores on refresh or focus and clears session-scoped queries and drafts on expiry or confirmed erasure. A missing activity record does not expire an otherwise valid session.

Session erasure clears cookies and removes the bootstrap record through the database ownership cascade. It does not erase the separate ADK development UI session. Full long-running chat recovery remains a later stage.

## Frontend behavior and current scope

The frontend includes welcome and timezone setup, responsive navigation, backend-driven overview statistics, basic history, source evidence and settings with confirmation-based erasure. Keyboard focus, a skip link, mobile menu accessibility, error states, offline messaging, retry keys and draft retention are implemented. No fictional user data is shown.

Full manual activity forms, filtering and editing interfaces, comparison charts, reduction interfaces and integrated application chat remain in their planned stages. Their navigation destinations clearly explain current availability. Direct API calculation, edit and reduction endpoints continue to work.

Build assets using pnpm build in frontend. FastAPI serves frontend/dist and falls back to index.html for application routes. Unknown API endpoints and missing assets still return errors. Do not publish the local application until later rate-limiting, deployment and operational stages are complete.
