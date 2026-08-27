"""CAG cache behavior against real Qdrant (local embedder)."""

from __future__ import annotations

import datetime

import pytest
from qdrant_client import AsyncQdrantClient

from sahana_api.cag.cache import CagCache
from sahana_api.embeddings.local import LocalEmbedder

pytestmark = pytest.mark.qdrant

_ROUTES = ["rag", "concierge", "web_search"]
_QUESTION = "What are the hospital visiting hours?"
_ANSWER = "General visiting hours are 11:00 to 13:00 and 16:00 to 19:00."


def _cache(
    client: AsyncQdrantClient,
    collection: str,
    embedder: LocalEmbedder,
    *,
    threshold: float = 0.9,
    ttl_seconds: int = 3600,
) -> CagCache:
    return CagCache(
        client,
        collection,
        embedder,
        similarity_threshold=threshold,
        ttl_seconds=ttl_seconds,
        cacheable_routes=_ROUTES,
    )


async def test_store_then_hit_increments_hit_count(
    qdrant_client: AsyncQdrantClient, collection_name: str, local_embedder: LocalEmbedder
) -> None:
    cache = _cache(qdrant_client, collection_name, local_embedder)
    assert await cache.store(_QUESTION, _ANSWER, "concierge") is True

    first = await cache.lookup(_QUESTION)
    assert first is not None
    assert first.answer == _ANSWER
    assert first.route == "concierge"
    assert first.score >= 0.9
    assert first.hit_count == 1

    second = await cache.lookup(_QUESTION)
    assert second is not None
    assert second.hit_count == 2


async def test_miss_below_threshold(
    qdrant_client: AsyncQdrantClient, collection_name: str, local_embedder: LocalEmbedder
) -> None:
    cache = _cache(qdrant_client, collection_name, local_embedder)
    await cache.store(_QUESTION, _ANSWER, "concierge")

    miss = await cache.lookup("What is the boiling point of water at sea level?")
    assert miss is None


async def test_route_filter_mismatch_is_miss(
    qdrant_client: AsyncQdrantClient, collection_name: str, local_embedder: LocalEmbedder
) -> None:
    cache = _cache(qdrant_client, collection_name, local_embedder)
    await cache.store(_QUESTION, _ANSWER, "concierge")

    assert await cache.lookup(_QUESTION, route="rag") is None
    hit = await cache.lookup(_QUESTION, route="concierge")
    assert hit is not None


async def test_non_allowlisted_route_is_not_stored(
    qdrant_client: AsyncQdrantClient, collection_name: str, local_embedder: LocalEmbedder
) -> None:
    cache = _cache(qdrant_client, collection_name, local_embedder)
    # CRM is patient-specific and must never be cached.
    assert cache.is_cacheable_route("crm") is False
    assert await cache.store("Who is my doctor?", "Dr. Perera", "crm") is False
    assert await cache.lookup("Who is my doctor?", route="crm") is None


async def test_expired_entry_is_a_miss(
    qdrant_client: AsyncQdrantClient, collection_name: str, local_embedder: LocalEmbedder
) -> None:
    cache = _cache(qdrant_client, collection_name, local_embedder)
    await cache.store(_QUESTION, _ANSWER, "concierge")

    points, _ = await qdrant_client.scroll(collection_name, limit=1, with_payload=False)
    past = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)).isoformat()
    await qdrant_client.set_payload(
        collection_name, payload={"expires_at": past}, points=[points[0].id]
    )

    assert await cache.lookup(_QUESTION) is None
    # The expired entry is pruned on the miss.
    assert (await qdrant_client.count(collection_name)).count == 0
