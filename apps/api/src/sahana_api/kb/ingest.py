"""Idempotent knowledge-base ingestion pipeline.

Run with ``python -m sahana_api.kb.ingest`` (or ``make ingest``). The pipeline
loads Markdown documents, splits them into token-aware chunks, embeds them with
the active KB embedder, and upserts them into ``sahana_kb`` with deterministic
point IDs derived from ``doc_id`` and chunk index. Re-running does not duplicate
points and updates changed chunks in place; documents that shrink have their
stale trailing chunks pruned. ``--recreate`` drops and rebuilds the collection,
which is required when the KB embedder (and therefore the vector dimension)
changes.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    Range,
)

from sahana_api.config import Settings, get_settings
from sahana_api.embeddings.base import Embedder
from sahana_api.embeddings.factory import build_kb_embedder
from sahana_api.kb.chunking import TokenChunker
from sahana_api.kb.documents import KbDocument, load_documents
from sahana_api.kb.retriever import (
    PAYLOAD_CHUNK_INDEX,
    PAYLOAD_CONTENT_HASH,
    PAYLOAD_DOC_ID,
    PAYLOAD_SECTION,
    PAYLOAD_SOURCE,
    PAYLOAD_TEXT,
    PAYLOAD_TITLE,
)
from sahana_api.logging import configure_logging, get_logger
from sahana_api.vector.client import create_qdrant_client
from sahana_api.vector.collections import ensure_collection

_logger = get_logger("sahana_api.kb.ingest")

# Repository-root data directory: apps/api/src/sahana_api/kb/ingest.py -> parents[5].
DEFAULT_KB_ROOT = Path(__file__).resolve().parents[5] / "data" / "kb"

# Fixed namespace for deterministic point IDs.
_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "kb.sahana.local")


@dataclass(frozen=True)
class _Chunk:
    index: int
    section: str
    text: str


@dataclass(frozen=True)
class IngestSummary:
    """Result of an ingestion run."""

    documents: int
    chunks: int
    collection: str
    dimension: int


def _point_id(doc_id: str, chunk_index: int) -> str:
    """Deterministic point ID for a (document, chunk index) pair."""
    return str(uuid.uuid5(_POINT_NAMESPACE, f"{doc_id}:{chunk_index}"))


def _chunk_document(document: KbDocument, chunker: TokenChunker) -> list[_Chunk]:
    """Chunk each section, assigning a running chunk index across the document."""
    chunks: list[_Chunk] = []
    index = 0
    for section in document.sections:
        for text in chunker.split(section.text):
            chunks.append(_Chunk(index=index, section=section.heading, text=text))
            index += 1
    return chunks


async def _prune_trailing(
    client: AsyncQdrantClient, collection: str, doc_id: str, kept: int
) -> None:
    """Delete any points for ``doc_id`` whose chunk index is >= ``kept``."""
    await client.delete(
        collection_name=collection,
        points_selector=FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(key=PAYLOAD_DOC_ID, match=MatchValue(value=doc_id)),
                    FieldCondition(key=PAYLOAD_CHUNK_INDEX, range=Range(gte=kept)),
                ]
            )
        ),
    )


async def ingest_knowledge_base(
    *,
    client: AsyncQdrantClient,
    collection: str,
    embedder: Embedder,
    chunker: TokenChunker,
    root: Path,
    recreate: bool = False,
) -> IngestSummary:
    """Ingest every document under ``root`` into ``collection`` idempotently."""
    if not root.is_dir():
        raise FileNotFoundError(f"KB directory does not exist: {root}")
    await ensure_collection(client, collection, dimension=embedder.dimension, recreate=recreate)

    documents = list(load_documents(root))
    total_chunks = 0
    for document in documents:
        chunks = _chunk_document(document, chunker)
        if chunks:
            vectors = await embedder.embed([chunk.text for chunk in chunks])
            points = [
                PointStruct(
                    id=_point_id(document.doc_id, chunk.index),
                    vector=vectors[position],
                    payload={
                        PAYLOAD_DOC_ID: document.doc_id,
                        PAYLOAD_TITLE: document.title,
                        PAYLOAD_SOURCE: document.source,
                        PAYLOAD_SECTION: chunk.section,
                        PAYLOAD_CHUNK_INDEX: chunk.index,
                        PAYLOAD_TEXT: chunk.text,
                        PAYLOAD_CONTENT_HASH: document.content_hash,
                    },
                )
                for position, chunk in enumerate(chunks)
            ]
            await client.upsert(collection_name=collection, points=points)
        await _prune_trailing(client, collection, document.doc_id, kept=len(chunks))
        total_chunks += len(chunks)

    summary = IngestSummary(
        documents=len(documents),
        chunks=total_chunks,
        collection=collection,
        dimension=embedder.dimension,
    )
    _logger.info(
        "kb.ingest.completed",
        documents=summary.documents,
        chunks=summary.chunks,
        collection=summary.collection,
        dimension=summary.dimension,
        embedder=embedder.model_name,
    )
    return summary


async def _run(settings: Settings, *, root: Path, recreate: bool) -> IngestSummary:
    """Wire dependencies from settings and run one ingestion pass."""
    embedder = build_kb_embedder(settings)
    chunker = TokenChunker(chunk_tokens=settings.kb_chunk_tokens, overlap=settings.kb_chunk_overlap)
    client = create_qdrant_client(settings)
    try:
        return await ingest_knowledge_base(
            client=client,
            collection=settings.qdrant_kb_collection,
            embedder=embedder,
            chunker=chunker,
            root=root,
            recreate=recreate,
        )
    finally:
        await client.close()


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Ingest the Sahana knowledge base into Qdrant.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection (required when the embedder dimension changes).",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_KB_ROOT,
        help=f"Directory of KB Markdown documents (default: {DEFAULT_KB_ROOT}).",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)
    asyncio.run(_run(settings, root=args.path, recreate=args.recreate))


if __name__ == "__main__":
    main()
