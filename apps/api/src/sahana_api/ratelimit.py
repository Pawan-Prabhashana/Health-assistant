"""Rate limiting for the expensive chat routes.

Keyed by hashed patient identity when a phone is present, falling back to the
client IP otherwise, so a signed-in caller is limited as themselves and anonymous
traffic is limited per source. The phone is hashed, never stored or logged in the
clear, so the limiter store carries no PII. The store is in-memory via the
``limits`` library, which means limits are per-process: running multiple api
replicas requires a shared store (Redis) — see the runbook. Over the limit the
caller gets a ``429`` with a ``Retry-After`` header.
"""

from __future__ import annotations

import hashlib
import math
import time

from limits import RateLimitItem, parse
from limits.aio.storage import MemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from starlette.requests import Request

from sahana_api.config import Settings


class RateLimitExceededError(Exception):
    """Raised when a caller exceeds the configured rate limit."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = retry_after


def _client_ip(request: Request) -> str:
    """Best-effort client IP, honouring the nginx-set X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client is not None else "unknown"


def _identity_key(phone: str | None, request: Request) -> str:
    """A non-PII rate-limit key: hashed identity when known, else client IP."""
    if phone:
        digest = hashlib.sha256(phone.strip().encode("utf-8")).hexdigest()[:16]
        return f"id:{digest}"
    return f"ip:{_client_ip(request)}"


class RateLimiter:
    """A moving-window rate limiter over an in-memory store."""

    def __init__(self, *, limit: str, enabled: bool) -> None:
        self._enabled = enabled
        self._item: RateLimitItem = parse(limit)
        self._limiter = MovingWindowRateLimiter(MemoryStorage())

    async def enforce(self, request: Request, phone: str | None) -> None:
        """Consume one unit for the caller; raise :class:`RateLimitExceededError` if over."""
        if not self._enabled:
            return
        key = _identity_key(phone, request)
        allowed = await self._limiter.hit(self._item, key)
        if not allowed:
            stats = await self._limiter.get_window_stats(self._item, key)
            retry_after = max(1, math.ceil(stats.reset_time - time.time()))
            raise RateLimitExceededError(retry_after)


def build_rate_limiter(settings: Settings) -> RateLimiter:
    """Construct the chat rate limiter from settings."""
    return RateLimiter(limit=settings.rate_limit_chat, enabled=settings.rate_limit_enabled)
