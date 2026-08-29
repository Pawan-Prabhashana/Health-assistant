"""Route-gated KNN-1 answer cache (CAG).

The CAG cache short-circuits repeat FAQs: a question is embedded with the local
(fastembed) embedder, matched against the nearest cached entry, and the cached
answer is returned only when it is similar enough, unexpired, and route-allowed.

Safety invariant (see ADR 0008): the cache holds only non-personalized,
non-PII answers. ``store`` refuses any route not in the cacheable allowlist, and
the allowlist excludes CRM (patient-specific) by default, so a personalized
answer is never written to the cache and therefore never served from it.
"""

from __future__ import annotations

import datetime
import uuid
from dataclasses import dataclass
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointIdsList, PointStruct

from sahana_api.embeddings.base import Embedder
from sahana_api.logging import get_logger
from sahana_api.vector.collections import ensure_collection

_logger = get_logger("sahana_api.cag")

_POINT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "cag.sahana.local")

_QUESTION = "question"
_ANSWER = "answer"
_ROUTE = "route"
_CREATED_AT = "created_at"
_EXPIRES_AT = "expires_at"
_HIT_COUNT = "hit_count"


@dataclass(frozen=True)
class CachedAnswer:
    """A cache hit: the stored answer plus its metadata and match score."""

    question: str
    answer: str
    route: str
    created_at: datetime.datetime
    expires_at: datetime.datetime | None
    hit_count: int
    score: float


@dataclass(frozen=True)
class CagCandidate:
    """The nearest cached entry from a route-agnostic, ungated KNN-1 peek.

    Unlike :meth:`CagCache.lookup`, a peek applies no threshold, TTL, or route
    gating and does not mutate the cache; the decision graph gates it at the
    fan-in (see ADR 0010).
    """

    answer: str
    route: str
    score: float
    expired: bool


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _point_id(question: str) -> str:
    """Deterministic id per normalized question so repeats overwrite in place."""
    return str(uuid.uuid5(_POINT_NAMESPACE, question.strip().lower()))


class CagCache:
    """KNN-1 cache over ``sahana_cag`` with threshold, TTL, and route-gating."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        collection: str,
        embedder: Embedder,
        *,
        similarity_threshold: float,
        ttl_seconds: int,
        cacheable_routes: list[str],
    ) -> None:
        self._client = client
        self._collection = collection
        self._embedder = embedder
        self._threshold = similarity_threshold
        self._ttl_seconds = ttl_seconds
        self._cacheable_routes = frozenset(cacheable_routes)
        self._provisioned = False

    def is_cacheable_route(self, route: str) -> bool:
        """Whether answers from ``route`` may be cached."""
        return route in self._cacheable_routes

    async def _ensure_collection(self) -> None:
        """Provision the CAG collection on first use (idempotent)."""
        if not self._provisioned:
            await ensure_collection(
                self._client, self._collection, dimension=self._embedder.dimension
            )
            self._provisioned = True

    async def store(self, question: str, answer: str, route: str) -> bool:
        """Cache an answer. Returns ``False`` (and stores nothing) for a non-allowlisted route."""
        if not self.is_cacheable_route(route):
            _logger.info("cag.store.rejected", route=route)
            return False

        await self._ensure_collection()
        vector = (await self._embedder.embed([question]))[0]
        created = _now()
        expires = (
            created + datetime.timedelta(seconds=self._ttl_seconds)
            if self._ttl_seconds > 0
            else None
        )
        payload: dict[str, Any] = {
            _QUESTION: question,
            _ANSWER: answer,
            _ROUTE: route,
            _CREATED_AT: created.isoformat(),
            _EXPIRES_AT: expires.isoformat() if expires is not None else None,
            _HIT_COUNT: 0,
        }
        await self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=_point_id(question), vector=vector, payload=payload)],
        )
        return True

    async def record_hit(self, question: str) -> None:
        """Increment ``hit_count`` on the entry nearest ``question`` (best-effort).

        Called post-gate for a served cache hit; ``peek`` stays non-mutating so the
        graph never has side effects. Failures are swallowed — this is accounting.
        """
        try:
            await self._ensure_collection()
            vector = (await self._embedder.embed([question]))[0]
            response = await self._client.query_points(
                collection_name=self._collection, query=vector, limit=1, with_payload=True
            )
            if not response.points or response.points[0].score < self._threshold:
                return
            top = response.points[0]
            hit_count = int((top.payload or {}).get(_HIT_COUNT, 0)) + 1
            await self._client.set_payload(
                collection_name=self._collection, payload={_HIT_COUNT: hit_count}, points=[top.id]
            )
        except Exception as exc:  # accounting must never break the response path
            _logger.warning("cag.record_hit.failed", error=type(exc).__name__)

    async def peek(self, question: str) -> CagCandidate | None:
        """Return the nearest cached candidate without gating or mutation.

        Applies no threshold, TTL, or route filter and does not increment
        ``hit_count`` — the decision graph gates the candidate at its fan-in.
        """
        await self._ensure_collection()
        vector = (await self._embedder.embed([question]))[0]
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=1,
            with_payload=True,
        )
        if not response.points:
            return None

        top = response.points[0]
        payload = top.payload or {}
        expires_at = (
            datetime.datetime.fromisoformat(payload[_EXPIRES_AT])
            if payload.get(_EXPIRES_AT) is not None
            else None
        )
        return CagCandidate(
            answer=str(payload[_ANSWER]),
            route=str(payload[_ROUTE]),
            score=top.score,
            expired=expires_at is not None and _now() > expires_at,
        )

    async def lookup(self, question: str, route: str | None = None) -> CachedAnswer | None:
        """Return a cached answer when one matches above threshold, unexpired, and route-allowed."""
        await self._ensure_collection()
        vector = (await self._embedder.embed([question]))[0]
        response = await self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=1,
            with_payload=True,
        )
        if not response.points:
            return None

        top = response.points[0]
        if top.score < self._threshold:
            return None

        payload = top.payload or {}
        stored_route = str(payload[_ROUTE])
        if not self.is_cacheable_route(stored_route):
            return None
        if route is not None and stored_route != route:
            return None

        expires_at = (
            datetime.datetime.fromisoformat(payload[_EXPIRES_AT])
            if payload.get(_EXPIRES_AT) is not None
            else None
        )
        if expires_at is not None and _now() > expires_at:
            await self._client.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=[top.id]),
            )
            return None

        hit_count = int(payload[_HIT_COUNT]) + 1
        await self._client.set_payload(
            collection_name=self._collection,
            payload={_HIT_COUNT: hit_count},
            points=[top.id],
        )
        return CachedAnswer(
            question=str(payload[_QUESTION]),
            answer=str(payload[_ANSWER]),
            route=stored_route,
            created_at=datetime.datetime.fromisoformat(payload[_CREATED_AT]),
            expires_at=expires_at,
            hit_count=hit_count,
            score=top.score,
        )
