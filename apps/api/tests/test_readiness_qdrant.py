"""Qdrant readiness reflects reachability; liveness stays independent."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from sahana_api.config import Settings
from sahana_api.main import create_app

UNREACHABLE_QDRANT_URL = "http://127.0.0.1:1"


async def test_readiness_down_when_qdrant_unreachable() -> None:
    app = create_app(
        Settings(app_env="development", log_json=False, qdrant_url=UNREACHABLE_QDRANT_URL)
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
    qdrant = next(check for check in body["checks"] if check["name"] == "qdrant")
    assert qdrant["ok"] is False
    assert qdrant["detail"] == "vector store unreachable"

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
