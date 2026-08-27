"""Qdrant client and vector-store handle."""

from __future__ import annotations

from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient

from sahana_api.config import Settings


class VectorStoreNotConfiguredError(RuntimeError):
    """Raised when vector-store access is attempted without a configured URL."""


def create_qdrant_client(settings: Settings, *, timeout: float = 10.0) -> AsyncQdrantClient:
    """Build an :class:`AsyncQdrantClient` from settings.

    :raises VectorStoreNotConfiguredError: if ``qdrant_url`` is unset.
    """
    if settings.qdrant_url is None:
        raise VectorStoreNotConfiguredError("SAHANA_QDRANT_URL is not configured")
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=int(timeout),
    )


@dataclass(slots=True)
class VectorStore:
    """Owns the Qdrant client and the KB/CAG collection names."""

    client: AsyncQdrantClient
    kb_collection: str
    cag_collection: str

    @classmethod
    def from_settings(cls, settings: Settings) -> VectorStore:
        """Build a :class:`VectorStore` from settings."""
        return cls(
            client=create_qdrant_client(settings),
            kb_collection=settings.qdrant_kb_collection,
            cag_collection=settings.qdrant_cag_collection,
        )

    async def close(self) -> None:
        """Close the underlying client."""
        await self.client.close()
