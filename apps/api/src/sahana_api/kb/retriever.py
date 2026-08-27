"""Knowledge retriever over the KB corpus.

``KnowledgeRetriever.search`` embeds a query with the KB embedder and runs a
similarity search against ``sahana_kb``, returning scored chunks with their
payload. It performs no grading — scores are returned so CRAG grading (Phase 5)
can threshold them later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient

from sahana_api.embeddings.base import Embedder

# Payload keys stored on every KB point. Shared with the ingestion pipeline so the
# write and read sides cannot drift.
PAYLOAD_DOC_ID = "doc_id"
PAYLOAD_TITLE = "title"
PAYLOAD_SOURCE = "source"
PAYLOAD_SECTION = "section"
PAYLOAD_CHUNK_INDEX = "chunk_index"
PAYLOAD_TEXT = "text"
PAYLOAD_CONTENT_HASH = "content_hash"


@dataclass(frozen=True)
class ScoredChunk:
    """A KB chunk with its similarity score and payload fields."""

    score: float
    doc_id: str
    title: str
    source: str
    section: str
    chunk_index: int
    text: str


def chunk_from_payload(score: float, payload: dict[str, Any]) -> ScoredChunk:
    """Build a :class:`ScoredChunk` from a Qdrant point score and payload."""
    return ScoredChunk(
        score=score,
        doc_id=str(payload[PAYLOAD_DOC_ID]),
        title=str(payload[PAYLOAD_TITLE]),
        source=str(payload[PAYLOAD_SOURCE]),
        section=str(payload[PAYLOAD_SECTION]),
        chunk_index=int(payload[PAYLOAD_CHUNK_INDEX]),
        text=str(payload[PAYLOAD_TEXT]),
    )


class KnowledgeRetriever:
    """Similarity search over the KB corpus."""

    def __init__(self, client: AsyncQdrantClient, collection: str, embedder: Embedder) -> None:
        self._client = client
        self._collection = collection
        self._embedder = embedder

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        """Return the ``top_k`` most similar chunks to ``query``, most similar first."""
        if top_k <= 0:
            return []
        vector = (await self._embedder.embed([query]))[0]
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=top_k,
            with_payload=True,
        )
        return [chunk_from_payload(point.score, point.payload or {}) for point in response.points]
