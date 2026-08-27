"""End-to-end KB ingestion and retrieval against real Qdrant (local embedder)."""

from __future__ import annotations

from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.kb.chunking import TokenChunker
from sahana_api.kb.ingest import ingest_knowledge_base
from sahana_api.kb.retriever import KnowledgeRetriever

pytestmark = pytest.mark.qdrant

_SKIN_QUERY = "How should staff perform a skin inspection on an admitted patient?"


async def test_ingest_and_retrieve_skin_inspection(
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
    token_chunker: TokenChunker,
    kb_root: Path,
) -> None:
    summary = await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=kb_root,
    )
    assert summary.documents == 4
    assert summary.chunks > 0
    assert summary.dimension == 384

    retriever = KnowledgeRetriever(qdrant_client, collection_name, local_embedder)
    results = await retriever.search(_SKIN_QUERY, top_k=3)

    assert results
    assert results[0].score > 0.0
    assert any(chunk.source == "procedures/skin-inspection" for chunk in results)


async def test_reingestion_is_idempotent(
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
    token_chunker: TokenChunker,
    kb_root: Path,
) -> None:
    first = await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=kb_root,
    )
    count_after_first = (await qdrant_client.count(collection_name)).count

    second = await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=kb_root,
    )
    count_after_second = (await qdrant_client.count(collection_name)).count

    assert first.chunks == second.chunks
    assert count_after_first == count_after_second


async def test_changed_chunk_updates_in_place(
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
    token_chunker: TokenChunker,
    tmp_path: Path,
) -> None:
    doc = tmp_path / "note.md"
    doc.write_text(
        "---\ntitle: Note\nsource: notes/one\n---\n\n## Body\n\nThe original wording here.\n",
        encoding="utf-8",
    )
    await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=tmp_path,
    )
    count_first = (await qdrant_client.count(collection_name)).count

    doc.write_text(
        "---\ntitle: Note\nsource: notes/one\n---\n\n## Body\n\nThe replacement wording here.\n",
        encoding="utf-8",
    )
    await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=tmp_path,
    )
    count_second = (await qdrant_client.count(collection_name)).count

    assert count_first == count_second == 1
    points, _ = await qdrant_client.scroll(collection_name, limit=10, with_payload=True)
    assert points[0].payload is not None
    assert "replacement wording" in points[0].payload["text"]
