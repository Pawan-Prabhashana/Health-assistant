"""Readiness reflects database reachability while liveness stays independent."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sahana_api.config import Settings
from sahana_api.main import create_app

# An address that refuses connections immediately, simulating an unreachable DB.
UNREACHABLE_DB_URL = "postgresql+asyncpg://sahana:sahana@127.0.0.1:1/sahana"


async def test_readiness_down_when_database_unreachable() -> None:
    app = create_app(
        Settings(
            app_env="development",
            log_json=False,
            database_url=UNREACHABLE_DB_URL,
            database_migration_url=UNREACHABLE_DB_URL,
        )
    )
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        ready = await client.get("/health/ready")
        live = await client.get("/health/live")

    assert ready.status_code == 503
    body = ready.json()
    assert body["ready"] is False
    postgres = next(check for check in body["checks"] if check["name"] == "postgres")
    assert postgres["ok"] is False
    assert postgres["detail"] == "database unreachable"

    # Liveness must stay up even when the database is misconfigured.
    assert live.status_code == 200
    assert live.json() == {"status": "alive"}


@pytest.mark.pg
async def test_readiness_up_when_database_reachable(pg_client: AsyncClient) -> None:
    response = await pg_client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    postgres = next(check for check in body["checks"] if check["name"] == "postgres")
    assert postgres["ok"] is True
    assert postgres["detail"] is None
