"""Shared pytest fixtures.

Two families of fixtures live here:

* Dependency-free fixtures (``settings``/``app``/``client``) that exercise the
  app through an in-process ASGI transport with no database — used by the health
  and unit tests.
* Postgres-backed fixtures (marked ``pg``) that spin a real ``pgvector`` Postgres
  via testcontainers, run ``alembic upgrade head`` once per session, and hand out
  transaction-isolated ``AsyncSession``s. These skip cleanly when Docker is
  absent and must pass when it is present.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from sahana_api.config import Settings
from sahana_api.db.session import get_session
from sahana_api.main import create_app

if TYPE_CHECKING:
    from testcontainers.postgres import PostgresContainer

API_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Dependency-free fixtures (no database)
# ---------------------------------------------------------------------------
@pytest.fixture
def settings() -> Settings:
    """Return deterministic settings for tests, with no database configured."""
    return Settings(
        app_env="development",
        log_level="INFO",
        log_json=False,
        cors_allow_origins=["http://localhost:8080"],
        database_url=None,
        database_migration_url=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    """Return a freshly constructed application for a single test."""
    return create_app(settings)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """Yield an ``AsyncClient`` bound to ``app`` via ASGI transport."""
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as async_client,
    ):
        yield async_client


# ---------------------------------------------------------------------------
# Postgres-backed fixtures (via testcontainers)
# ---------------------------------------------------------------------------
def _async_url(container: PostgresContainer) -> str:
    """Build an asyncpg URL for the running container."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(5432)
    return f"postgresql+asyncpg://sahana:sahana@{host}:{port}/sahana"


def alembic_config(url: str) -> Config:
    """Return an Alembic config pointed at ``url`` and the project's scripts."""
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    """Start a pgvector Postgres for the test session; skip if Docker is absent."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:  # pragma: no cover - import guard
        pytest.skip("testcontainers is not installed")

    container = PostgresContainer(
        "pgvector/pgvector:pg16",
        username="sahana",
        password="sahana",
        dbname="sahana",
    )
    try:
        container.start()
    except Exception as exc:  # Docker unavailable or image cannot start.
        pytest.skip(f"Docker/Postgres container unavailable: {type(exc).__name__}")
    try:
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
def migrated_url(postgres_container: PostgresContainer) -> str:
    """Run ``alembic upgrade head`` once against the container and return its URL."""
    url = _async_url(postgres_container)
    command.upgrade(alembic_config(url), "head")
    return url


@pytest.fixture
async def db_engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    """Provide an engine bound to the migrated container database."""
    engine = create_async_engine(
        migrated_url,
        poolclass=NullPool,
        connect_args={"statement_cache_size": 0},
    )
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a session wrapped in an outer transaction that is always rolled back.

    ``join_transaction_mode="create_savepoint"`` lets repository/endpoint commits
    proceed as savepoints inside the outer transaction, so each test sees a clean
    database regardless of what the code under test commits.
    """
    connection: AsyncConnection = await db_engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()


@pytest.fixture
async def pg_client(migrated_url: str, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Yield a client whose app is DB-backed, with ``get_session`` bound to the test session."""
    app = create_app(
        Settings(
            app_env="development",
            log_level="INFO",
            log_json=False,
            database_url=migrated_url,
            database_migration_url=migrated_url,
        )
    )

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as async_client,
    ):
        yield async_client
