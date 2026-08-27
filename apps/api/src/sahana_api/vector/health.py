"""Qdrant readiness check."""

from __future__ import annotations

import asyncio

from qdrant_client import AsyncQdrantClient

from sahana_api.logging import get_logger
from sahana_api.readiness import DependencyCheck
from sahana_api.schemas.health import Check

_logger = get_logger("sahana_api.vector.health")


def make_qdrant_check(client: AsyncQdrantClient, *, timeout: float = 2.0) -> DependencyCheck:
    """Return a readiness check that lists collections with a short timeout.

    The detail is generic so no URL or credential fragment reaches the response.
    """

    async def check() -> Check:
        try:
            await asyncio.wait_for(client.get_collections(), timeout=timeout)
        except Exception as exc:  # any failure (timeout, connection) means not-ready
            _logger.warning("readiness.qdrant.unreachable", error=type(exc).__name__)
            return Check(name="qdrant", ok=False, detail="vector store unreachable")
        return Check(name="qdrant", ok=True, detail=None)

    return check
