"""Alembic migration environment.

The migration URL is resolved from the application :class:`Settings`
(``database_migration_url``, the direct/non-pooled connection) unless a
``sqlalchemy.url`` is set explicitly on the Alembic Config — which the test suite
does to point at its ephemeral Postgres container. Migrations run against the
direct connection because DDL needs a stable session the transaction pooler does
not provide.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from sahana_api.config import get_settings
from sahana_api.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    """Return the migration URL from the Config or application settings."""
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    settings = get_settings()
    if settings.database_migration_url is None:
        raise RuntimeError("SAHANA_DATABASE_MIGRATION_URL is not configured")
    return settings.database_migration_url


def run_migrations_offline() -> None:
    """Emit SQL for migrations without a live connection."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    """Configure the context on a live connection and run migrations."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async connection."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _resolve_url()
    engine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
