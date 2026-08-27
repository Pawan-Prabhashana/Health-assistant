"""FastAPI application factory and process entrypoint.

``create_app`` wires configuration, structured logging, CORS, the database,
readiness registry, error handlers, and routers together. The lifespan handler
owns startup and shutdown so the same construction path is used by the ASGI
server and the test suite. The application boots even without a database
configured: liveness stays up and readiness reports Postgres as not-ready.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sahana_api.config import Settings, get_settings
from sahana_api.db.engine import Database
from sahana_api.db.health import make_postgres_check
from sahana_api.errors import register_exception_handlers
from sahana_api.llm.health import make_llm_check
from sahana_api.llm.registry import ModelRegistry, build_model_registry
from sahana_api.logging import configure_logging, get_logger
from sahana_api.readiness import ReadinessRegistry
from sahana_api.routers import health_router, patients_router, sessions_router
from sahana_api.vector.client import VectorStore
from sahana_api.vector.health import make_qdrant_check
from sahana_api.version import __version__


class RootResponse(TypedDict):
    """Courtesy landing payload returned from ``GET /``."""

    name: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging, open the database, and register readiness checks."""
    settings: Settings = app.state.settings
    configure_logging(settings)
    logger = get_logger("sahana_api.lifespan")

    registry: ReadinessRegistry = app.state.readiness
    database: Database | None = None
    if settings.database_url is not None:
        database = Database.from_settings(settings)
        registry.register(make_postgres_check(database))
        logger.info("database.configured")
    else:
        logger.warning("database.not_configured")
    app.state.db = database

    vector: VectorStore | None = None
    if settings.qdrant_url is not None:
        vector = VectorStore.from_settings(settings)
        registry.register(make_qdrant_check(vector.client))
        logger.info("vector_store.configured")
    else:
        logger.warning("vector_store.not_configured")
    app.state.vector = vector

    # The LLM registry is always built (fake or live) and its readiness check is
    # always registered; missing live config makes readiness not-ready.
    models: ModelRegistry = build_model_registry(settings)
    registry.register(make_llm_check(settings))
    app.state.llm = models
    logger.info("llm.configured", mode=settings.llm_mode, roles=sorted(models.configured_roles()))

    logger.info(
        "application.startup",
        app_name=settings.app_name,
        app_env=settings.app_env,
        version=__version__,
    )
    try:
        yield
    finally:
        if database is not None:
            await database.dispose()
        if vector is not None:
            await vector.close()
        await models.aclose()
        logger.info("application.shutdown", version=__version__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and return a configured :class:`FastAPI` application.

    A ``settings`` instance may be supplied to override the cached singleton,
    which keeps tests hermetic.
    """
    resolved = settings or get_settings()

    app = FastAPI(
        title=resolved.app_name,
        version=__version__,
        summary="Hospital health assistant API.",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.readiness = ReadinessRegistry()
    app.state.db = None
    app.state.vector = None
    app.state.llm = None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(patients_router)
    app.include_router(sessions_router)

    @app.get("/", summary="Service landing", tags=["meta"])
    async def root() -> RootResponse:
        """Return the service name and version. Not a counted API endpoint."""
        return {"name": resolved.app_name, "version": __version__}

    return app


app = create_app()
