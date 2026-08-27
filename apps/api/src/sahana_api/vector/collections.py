"""Collection provisioning.

Collections are created at the dimension reported by their active embedder, with
cosine distance. Provisioning is idempotent: an existing collection is left in
place unless ``recreate`` is requested (used when the KB embedder — and therefore
the vector dimension — changes).
"""

from __future__ import annotations

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from sahana_api.logging import get_logger

_logger = get_logger("sahana_api.vector.collections")


async def ensure_collection(
    client: AsyncQdrantClient,
    name: str,
    *,
    dimension: int,
    recreate: bool = False,
) -> bool:
    """Ensure a cosine collection ``name`` of ``dimension`` exists.

    Returns ``True`` if the collection was created (or recreated), ``False`` if it
    already existed and was left untouched.
    """
    exists = await client.collection_exists(name)
    if exists and recreate:
        await client.delete_collection(name)
        _logger.info("collection.dropped", collection=name)
        exists = False
    if exists:
        return False

    await client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
    )
    _logger.info("collection.created", collection=name, dimension=dimension)
    return True
