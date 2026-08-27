"""Collection provisioning and Qdrant readiness (real Qdrant)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams

from sahana_api.config import Settings
from sahana_api.main import create_app
from sahana_api.vector.collections import ensure_collection

pytestmark = pytest.mark.qdrant


async def _vector_size(client: AsyncQdrantClient, collection: str) -> int:
    info = await client.get_collection(collection)
    params = info.config.params.vectors
    assert isinstance(params, VectorParams)
    return params.size


async def test_ensure_collection_creates_at_dimension_and_is_idempotent(
    qdrant_client: AsyncQdrantClient, collection_name: str
) -> None:
    created = await ensure_collection(qdrant_client, collection_name, dimension=384)
    assert created is True
    assert await qdrant_client.collection_exists(collection_name)
    assert await _vector_size(qdrant_client, collection_name) == 384

    again = await ensure_collection(qdrant_client, collection_name, dimension=384)
    assert again is False


async def test_recreate_changes_dimension(
    qdrant_client: AsyncQdrantClient, collection_name: str
) -> None:
    await ensure_collection(qdrant_client, collection_name, dimension=384)
    recreated = await ensure_collection(
        qdrant_client, collection_name, dimension=1536, recreate=True
    )
    assert recreated is True
    assert await _vector_size(qdrant_client, collection_name) == 1536


async def test_readiness_reports_qdrant_up(qdrant_url: str) -> None:
    app = create_app(Settings(app_env="development", log_json=False, qdrant_url=qdrant_url))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    qdrant = next(check for check in body["checks"] if check["name"] == "qdrant")
    assert qdrant["ok"] is True
