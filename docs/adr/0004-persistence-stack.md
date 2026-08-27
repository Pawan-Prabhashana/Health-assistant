# 4. Persistence stack

- Status: Accepted
- Date: 2026-08-26

## Context

Phase 1 introduces durable state: patients, appointments, conversation sessions,
and messages. The application is asynchronous and fans out concurrent work per
request, so the data layer must be async-native. The target database is Supabase
Postgres, reached in production through the Supabase connection pooler
(pgbouncer, transaction mode). We also need repeatable, reviewable schema
migrations.

## Decision

Use **SQLAlchemy 2.0 (async)** with the **asyncpg** driver and **Alembic** for
migrations. Models use the typed `Mapped[...]` / `mapped_column(...)` style.
Pydantic v2 schemas are kept strictly separate from ORM models: endpoints never
serialize an ORM object directly, they map it through a response schema.

Two connection strings are configured (both `postgresql+asyncpg`):

- `database_url` — the pooled runtime connection (transaction pooler, port 6543).
- `database_migration_url` — a direct/session connection (port 5432) used only by
  Alembic, because DDL needs a stable session the transaction pooler cannot give.

Pgbouncer in transaction mode is incompatible with server-side prepared
statements, so the runtime engine is created with
`connect_args={"statement_cache_size": 0}`, disabling asyncpg's prepared-statement
cache. The engine also enables `pool_pre_ping` and is sized from settings
(`db_pool_size`, `db_max_overflow`, `db_pool_timeout`).

Alembic reads its URL from the application `Settings` (not a hardcoded value in
`alembic.ini`); the test suite overrides it programmatically to point at an
ephemeral container.

All datetime columns are `timestamptz`. Row-write timestamps default to
`clock_timestamp()` (the wall clock at write time) rather than `now()` (fixed to
the transaction start), so rows created in one transaction receive strictly
increasing timestamps and "newest first" ordering is deterministic.

## Consequences

- One clean HTTP round-trip maps onto async DB access with correct
  commit/rollback owned by a single request-scoped `get_session` dependency.
- The prepared-statement pitfall behind the Supabase pooler is handled once, in
  the engine factory, rather than rediscovered per query.
- Migrations are reproducible and are exercised in CI against a real `pgvector`
  Postgres (`alembic upgrade head` on a fresh database, plus a full up/down/up
  cycle).
- Two connection strings add deployment surface; `.env.example` documents which
  is used where and why.
