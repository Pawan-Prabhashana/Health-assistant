"""Verify the initial migration applies and reverses cleanly on a fresh database."""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

pytestmark = pytest.mark.pg

API_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_TABLES = {"patients", "appointments", "sessions", "messages"}


def _alembic_config(async_url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", async_url)
    return config


def _table_names(sync_url: str) -> set[str]:
    engine = create_engine(sync_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_then_downgrade_cycle() -> None:
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - import guard
        pytest.skip("testcontainers is not installed")

    container = PostgresContainer(
        "pgvector/pgvector:pg16", username="sahana", password="sahana", dbname="sahana"
    )
    try:
        container.start()
    except Exception as exc:  # Docker unavailable.
        pytest.skip(f"Docker/Postgres container unavailable: {type(exc).__name__}")

    try:
        host = container.get_container_host_ip()
        port = container.get_exposed_port(5432)
        async_url = f"postgresql+asyncpg://sahana:sahana@{host}:{port}/sahana"
        sync_url = f"postgresql+psycopg2://sahana:sahana@{host}:{port}/sahana"
        config = _alembic_config(async_url)

        command.upgrade(config, "head")
        assert _table_names(sync_url) >= SCHEMA_TABLES

        command.downgrade(config, "base")
        assert not (SCHEMA_TABLES & _table_names(sync_url))

        # Re-applying proves the migration is repeatable from scratch.
        command.upgrade(config, "head")
        assert _table_names(sync_url) >= SCHEMA_TABLES
    finally:
        container.stop()
