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

import asyncio
import time
import urllib.request
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.db.session import get_session
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.graph.pipeline import build_graph
from sahana_api.kb.chunking import TokenChunker
from sahana_api.llm.registry import ModelRegistry
from sahana_api.main import create_app
from sahana_api.tools.rag import Retriever
from sahana_api.tools.tavily import FakeTavilyClient
from sahana_api.tools.wiring import build_real_deps

if TYPE_CHECKING:
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.core.container import DockerContainer

API_ROOT = Path(__file__).resolve().parents[1]
KB_ROOT = API_ROOT.parents[1] / "data" / "kb"


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
        llm_mode="fake",
        tavily_mode="fake",
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
        from testcontainers.community.postgres import PostgresContainer
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
            llm_mode="fake",
            tavily_mode="fake",
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


# ---------------------------------------------------------------------------
# Qdrant-backed fixtures (via testcontainers)
# ---------------------------------------------------------------------------
def _wait_for_http(url: str, *, timeout: float = 30.0) -> None:
    """Poll ``url`` until it returns HTTP 200 or the timeout elapses."""
    deadline = time.monotonic() + timeout
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # not ready yet
            last_error = type(exc).__name__
        time.sleep(0.5)
    raise RuntimeError(f"Qdrant did not become ready: {last_error}")


@pytest.fixture(scope="session")
def qdrant_url() -> Iterator[str]:
    """Start a Qdrant container for the session; skip if Docker is absent."""
    try:
        from testcontainers.core.container import DockerContainer
    except ImportError:  # pragma: no cover - import guard
        pytest.skip("testcontainers is not installed")

    container: DockerContainer = DockerContainer("qdrant/qdrant:v1.12.4").with_exposed_ports(6333)
    try:
        container.start()
    except Exception as exc:  # Docker unavailable or image cannot start.
        pytest.skip(f"Docker/Qdrant container unavailable: {type(exc).__name__}")
    try:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(6333))
        url = f"http://{host}:{port}"
        _wait_for_http(f"{url}/readyz")
        yield url
    finally:
        container.stop()


@pytest.fixture
async def qdrant_client(qdrant_url: str) -> AsyncIterator[AsyncQdrantClient]:
    """Yield an async Qdrant client bound to the container."""
    client = AsyncQdrantClient(url=qdrant_url)
    try:
        yield client
    finally:
        await client.close()


@pytest.fixture
def collection_name() -> str:
    """Return a unique collection name so tests do not interfere."""
    return f"test_{uuid.uuid4().hex}"


@pytest.fixture(scope="session")
def local_embedder() -> LocalEmbedder:
    """Return a shared local (fastembed) embedder; downloads the model once."""
    return LocalEmbedder()


@pytest.fixture
def kb_root() -> Path:
    """Return the KB data directory, skipping if it is not present."""
    if not KB_ROOT.exists():
        pytest.skip("KB data directory not found")
    return KB_ROOT


@pytest.fixture
def token_chunker() -> TokenChunker:
    """Return a TokenChunker, skipping if the tiktoken vocabulary is unavailable."""
    try:
        return TokenChunker(chunk_tokens=256, overlap=32)
    except Exception as exc:  # tiktoken vocabulary unavailable offline
        pytest.skip(f"tiktoken unavailable: {type(exc).__name__}")


# ---------------------------------------------------------------------------
# Chat pipeline fixtures (a DB-backed chat app bound to the isolated test session)
# ---------------------------------------------------------------------------
class _LockedSession:
    """Yields the shared test session under a lock so concurrent graph nodes do not
    overlap operations on a single ``AsyncSession`` (production uses one session per
    node from the sessionmaker, so this lock is test-only)."""

    def __init__(self, session: AsyncSession, lock: asyncio.Lock) -> None:
        self._session = session
        self._lock = lock

    async def __aenter__(self) -> AsyncSession:
        await self._lock.acquire()
        return self._session

    async def __aexit__(self, *exc: object) -> bool:
        self._lock.release()
        return False


class _SessionProviderDatabase:
    """A stand-in for ``Database`` exposing a ``sessionmaker`` over the test session."""

    def __init__(self, provider: Callable[[], _LockedSession]) -> None:
        self.sessionmaker = provider


ChatClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def session_provider(db_session: AsyncSession) -> Callable[[], _LockedSession]:
    """A serialized session provider over the transaction-isolated test session."""
    lock = asyncio.Lock()
    return lambda: _LockedSession(db_session, lock)


@pytest.fixture
def build_chat_client(
    db_session: AsyncSession, session_provider: Callable[[], _LockedSession]
) -> ChatClientFactory:
    """Return a factory building a chat-ready app bound to the test session.

    Usage: ``async with build_chat_client(models, cag=..., retriever=...) as client:``
    """

    @asynccontextmanager
    async def factory(
        models: ModelRegistry,
        *,
        cag: CagCache | None = None,
        retriever: Retriever | None = None,
    ) -> AsyncIterator[AsyncClient]:
        settings = Settings(llm_mode="fake", tavily_mode="fake", kb_embedder="local")
        deps = build_real_deps(
            settings,
            models,
            cag,
            session_provider=session_provider,
            retriever=retriever,
            tavily=FakeTavilyClient(),
        )
        app = create_app(settings)
        app.state.llm = models
        app.state.cag = cag
        app.state.db = _SessionProviderDatabase(session_provider)
        app.state.graph = build_graph(deps)

        async def _override() -> AsyncIterator[AsyncSession]:
            yield db_session

        app.dependency_overrides[get_session] = _override
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            yield client

    return factory
