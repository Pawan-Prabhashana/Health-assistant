"""Tests for the health and configuration endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from sahana_api.schemas.health import Check
from sahana_api.version import __version__

# Substrings that must never appear in a /config response key. Guards against a
# future change accidentally serialising a secret through the config endpoint.
_SECRET_MARKERS = ("key", "secret", "token", "password", "url", "dsn", "database")


async def test_liveness_shape_and_status(client: AsyncClient) -> None:
    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


async def test_readiness_ready_path(client: AsyncClient) -> None:
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body == {"ready": True, "checks": []}


async def test_readiness_reports_failing_dependency(app: FastAPI, client: AsyncClient) -> None:
    """A registered failing check flips readiness to false and yields 503."""

    async def failing_check() -> Check:
        return Check(name="postgres", ok=False, detail="connection refused")

    app.state.readiness.register(failing_check)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["ready"] is False
    assert body["checks"] == [{"name": "postgres", "ok": False, "detail": "connection refused"}]


async def test_config_contains_expected_keys(client: AsyncClient) -> None:
    response = await client.get("/config")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"app_name", "app_env", "version", "log_level", "features"}
    assert body["app_name"] == "Sahana"
    assert body["app_env"] == "development"
    assert body["version"] == __version__
    assert isinstance(body["features"], dict)


async def test_config_excludes_secrets(client: AsyncClient) -> None:
    response = await client.get("/config")
    body = response.json()

    for key in body:
        lowered = key.lower()
        assert not any(marker in lowered for marker in _SECRET_MARKERS), key
    # The values must not contain provider secrets either.
    serialized = response.text.lower()
    for marker in ("supabase", "qdrant", "groq", "openrouter", "openai", "tavily"):
        assert marker not in serialized, marker


async def test_root_landing(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"name": "Sahana", "version": __version__}


@pytest.mark.parametrize("path", ["/health/live", "/health/ready", "/config", "/"])
async def test_endpoints_return_json(client: AsyncClient, path: str) -> None:
    response = await client.get(path)

    assert response.headers["content-type"].startswith("application/json")
