"""The closed CAG loop: cacheable answers are stored, identical FAQs hit cache."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.cag.cache import CagCache
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.kb.retriever import ScoredChunk
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry
from sahana_api.repositories.sessions import SessionRepository
from tests.conftest import ChatClientFactory

pytestmark = [pytest.mark.pg, pytest.mark.qdrant]

_IN_SCOPE = {"in_scope": True, "category": "clinical", "reason": "hospital"}
_CHUNK = ScoredChunk(
    score=0.9,
    doc_id="skin",
    title="Skin Inspection Procedure",
    source="procedures/skin-inspection",
    section="Steps",
    chunk_index=0,
    text="Obtain consent, then inspect the skin systematically.",
)


class _FakeRetriever:
    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        return [_CHUNK][:top_k]


def _models(*, route: str = "rag", synth_text: str = "Grounded answer.") -> ModelRegistry:
    return ModelRegistry(
        {
            "guardrail": FakeChatModel(
                role="guardrail",
                structured_by_schema={
                    "GuardrailVerdict": _IN_SCOPE,
                    "RelevanceGrades": {"grades": [{"index": 0, "relevant": True}]},
                },
            ),
            "router": FakeChatModel(
                role="router",
                structured_payload={
                    "route": route,
                    "confidence": 0.9,
                    "reason": "r",
                    "needs_patient_identity": route == "crm",
                },
            ),
            "synth": FakeChatModel(role="synth", text=synth_text),
        }
    )


def _cache(client: AsyncQdrantClient, collection: str, embedder: LocalEmbedder) -> CagCache:
    return CagCache(
        client,
        collection,
        embedder,
        similarity_threshold=0.9,
        ttl_seconds=3600,
        cacheable_routes=["rag", "concierge", "web_search"],
    )


async def _new_session(db_session: AsyncSession) -> uuid.UUID:
    thread = await SessionRepository(db_session).create(None, "Chat")
    await db_session.flush()
    return thread.id


async def _point_payloads(client: AsyncQdrantClient, collection: str) -> list[dict[str, Any]]:
    points, _ = await client.scroll(collection, limit=100, with_payload=True)
    return [point.payload or {} for point in points]


async def test_miss_then_store_then_hit(
    build_chat_client: ChatClientFactory,
    db_session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
) -> None:
    session_id = await _new_session(db_session)
    cag = _cache(qdrant_client, collection_name, local_embedder)
    question = "What is the procedure for a skin inspection?"

    async with build_chat_client(
        _models(route="rag", synth_text="Inspect the skin systematically."),
        cag=cag,
        retriever=_FakeRetriever(),
    ) as client:
        first = await client.post(
            "/chat", json={"session_id": str(session_id), "message": question}
        )
        assert first.json()["verdict"] == "proceed"  # cache miss → tool path

        second = await client.post(
            "/chat", json={"session_id": str(session_id), "message": question}
        )

    body = second.json()
    assert body["verdict"] == "cache_hit"  # served from cache
    assert body["answer"] == "Inspect the skin systematically."

    # The served hit incremented hit_count (non-blocking, post-gate).
    payloads = await _point_payloads(qdrant_client, collection_name)
    assert len(payloads) == 1
    assert payloads[0]["route"] == "rag"
    assert payloads[0]["hit_count"] == 1


async def test_crm_answer_is_never_stored(
    build_chat_client: ChatClientFactory,
    db_session: AsyncSession,
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
) -> None:
    session_id = await _new_session(db_session)
    cag = _cache(qdrant_client, collection_name, local_embedder)

    async with build_chat_client(_models(route="crm"), cag=cag) as client:
        await client.post(
            "/chat", json={"session_id": str(session_id), "message": "Do I have an appointment?"}
        )

    payloads = await _point_payloads(qdrant_client, collection_name)
    assert all(payload.get("route") != "crm" for payload in payloads)
