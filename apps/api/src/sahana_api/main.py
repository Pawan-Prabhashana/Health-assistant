"""FastAPI application factory and process entrypoint.

``create_app`` wires configuration, structured logging, CORS, the readiness
registry, and the routers together. The lifespan handler owns startup and
shutdown so the same construction path is used by the ASGI server and the test
suite.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sahana_api.config import Settings, get_settings
from sahana_api.logging import configure_logging, get_logger
from sahana_api.readiness import ReadinessRegistry
from sahana_api.routers import health_router
from sahana_api.version import __version__


class RootResponse(TypedDict):
    """Courtesy landing payload returned from ``GET /``."""

    name: str
    version: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Configure logging on startup and log lifecycle events."""
    settings: Settings = app.state.settings
    configure_logging(settings)
    logger = get_logger("sahana_api.lifespan")
    logger.info(
        "application.startup",
        app_name=settings.app_name,
        app_env=settings.app_env,
        version=__version__,
    )
    try:
        yield
    finally:
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)

    @app.get("/", summary="Service landing", tags=["meta"])
    async def root() -> RootResponse:
        """Return the service name and version. Not a counted API endpoint."""
        return {"name": resolved.app_name, "version": __version__}

    return app


app = create_app()
