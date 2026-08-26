"""Shared pytest fixtures.

Tests exercise the application through an in-process ASGI transport, so no
network socket or running server is required. Each test receives a freshly built
app with explicit settings, keeping the suite independent of the ambient
environment.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sahana_api.config import Settings
from sahana_api.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Return deterministic settings for tests."""
    return Settings(
        app_env="development",
        log_level="INFO",
        log_json=False,
        cors_allow_origins=["http://localhost:8080"],
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
