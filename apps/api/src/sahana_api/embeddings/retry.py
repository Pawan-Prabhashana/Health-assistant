"""Async retry helper with timeout and latency logging.

Shared by the embedder implementations so both apply the same bounded-retry,
timeout, and latency-logging policy around their (network or local-compute)
embedding call.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import perf_counter

from sahana_api.embeddings.base import EmbeddingError
from sahana_api.logging import get_logger

_logger = get_logger("sahana_api.embeddings")


async def run_with_retries[T](
    operation: Callable[[], Awaitable[T]],
    *,
    event: str,
    attempts: int,
    timeout: float,
    base_delay: float = 0.5,
) -> T:
    """Run ``operation`` with a per-attempt timeout and bounded retries.

    Logs one latency line on success and a warning per failed attempt. Raises
    :class:`EmbeddingError` when all attempts are exhausted.
    """
    last_error: BaseException | None = None
    for attempt in range(1, attempts + 1):
        started = perf_counter()
        try:
            result = await asyncio.wait_for(operation(), timeout=timeout)
        except Exception as exc:
            last_error = exc
            _logger.warning(f"{event}.attempt_failed", attempt=attempt, error=type(exc).__name__)
            if attempt < attempts:
                await asyncio.sleep(base_delay * attempt)
            continue
        _logger.info(
            f"{event}.ok",
            attempt=attempt,
            latency_ms=round((perf_counter() - started) * 1000, 1),
        )
        return result

    raise EmbeddingError(f"{event} failed after {attempts} attempts") from last_error
