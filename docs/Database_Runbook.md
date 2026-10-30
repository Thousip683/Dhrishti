# Carbon Coach Database Runbook

## Local SQLite

Set STORAGE_MODE=database and DATABASE_URL=sqlite:///./carbon_coach.db in `.env`. Run `uv run alembic upgrade head` before starting the API. `/readyz` returns 503 if required tables are unavailable. SQLite enables foreign keys and WAL mode and serializes session transactions using BEGIN IMMEDIATE. This is appropriate for the local application, not a high-concurrency hosted deployment.

## PostgreSQL

Set DATABASE_URL to a PostgreSQL connection URL using the psycopg driver, such as `postgresql+psycopg://USER:PASSWORD@HOST/DATABASE`. Keep the real URL out of Git and routine logs. Apply the same Alembic migration before starting the API. Use database credentials with the required application permissions; use a controlled migration identity in a deployed environment.

Sessions, immutable calculation receipts, activities, idempotency responses, correction history and request foundations are normalized tables. Numeric emissions use numeric(20,6). Factor snapshots preserve source precision and provenance in JSON. Ownership foreign keys and unique calculation commits protect ledger consistency.

PostgreSQL requests lock the session row with NOWAIT. An overlapping request may receive SESSION_BUSY and should retry using its original idempotency key. Request recovery, shorter chat transactions and worker scheduling belong to Stage 7. Do not add multiple application workers relying only on asyncio locks.

## Migrations

Use `uv run alembic current` to inspect the applied revision and `uv run alembic upgrade head` to apply approved migrations. The baseline is 0001_durable_ledger and the latest revision is 0002_browser_sessions. Review future migration scripts and take a recoverable backup before applying schema changes to important data. Schema downgrade can remove data and is not part of routine rollback. Do not use metadata.create_all as a replacement for migrations.

## Retention and erasure

Anonymous sessions expire after 24 hours of inactivity. Successful authorized requests extend expiry. A background task sweeps up to 100 expired sessions every minute; database cascades delete receipts, logs, idempotency records, corrections and request records. Adapter-owned conversation context is erased through the gateway interface where available. Primary-store erasure does not make a claim about future production backup retention; define that policy before deployment.

API session deletion invalidates its credential and removes dependent records in the same database transaction. A successful deletion must be verified by a subsequent inaccessible-session response. The local ADK development UI has an independent session store.

## Tests

`uv run pytest -q` uses temporary SQLite databases and isolated memory stores and never modifies the developer's database. To include PostgreSQL tests, set TEST_POSTGRES_ADMIN_URL to an explicitly disposable test server. The test identity needs CREATE DATABASE privileges. Each case creates its own database named carbon_test followed by a unique suffix, applies migrations and drops only that database afterward. Never point this setting at a production server.

The initial implementation was verified using a separate local PostgreSQL 18 cluster; it did not inspect or modify existing user databases. Temporary database cluster files are excluded from Git.
