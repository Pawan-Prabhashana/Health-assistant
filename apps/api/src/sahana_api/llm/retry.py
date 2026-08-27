"""Retry/backoff policy for LLM calls.

Only transient failures are retried: per-attempt timeouts, connection errors,
HTTP 429, and 5xx. Any other 4xx fails fast. Backoff is bounded exponential with
full jitter; ``Retry-After`` is respected on 429. The policy is a small unit so
it can be tested in isolation without a live provider.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from sahana_api.llm.base import LLMError, LLMTimeoutError
from sahana_api.logging import get_logger

_logger = get_logger("sahana_api.llm.retry")

Sleeper = Callable[[float], Awaitable[None]]
Rng = Callable[[], float]


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff with full jitter."""

    max_retries: int
    base_delay: float = 0.5
    max_delay: float = 8.0
    jitter: float = 0.5


def is_transient(exc: BaseException) -> bool:
    """Return whether ``exc`` is a retryable transient failure."""
    if isinstance(exc, APITimeoutError | APIConnectionError | RateLimitError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


def retry_after_seconds(exc: BaseException) -> float | None:
    """Extract a ``Retry-After`` delay (seconds) from a 429, if present."""
    if not isinstance(exc, RateLimitError):
        return None
    header = exc.response.headers.get("retry-after")
    if header is None:
        return None
    try:
        return float(header)
    except ValueError:
        return None


def _delay(attempt: int, policy: RetryPolicy, retry_after: float | None, rng: Rng) -> float:
    """Compute the sleep before the next attempt (0-based ``attempt``)."""
    if retry_after is not None:
        return retry_after
    # 2.0 (not 2) keeps the exponentiation typed as float (int ** int is Any in typeshed).
    capped = min(policy.base_delay * (2.0**attempt), policy.max_delay)
    return capped + rng() * policy.jitter


async def run_with_policy[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy,
    timeout: float,
    event: str,
    sleep: Sleeper = asyncio.sleep,
    rng: Rng = random.random,
) -> T:
    """Run ``operation`` with a per-attempt timeout and the retry policy.

    :raises LLMTimeoutError: when the final attempt times out.
    :raises Exception: the original error for a non-transient failure or the last
        transient failure after retries are exhausted.
    """
    for attempt in range(policy.max_retries + 1):
        try:
            return await asyncio.wait_for(operation(), timeout=timeout)
        except TimeoutError as exc:
            if attempt >= policy.max_retries:
                raise LLMTimeoutError(f"{event} timed out after {timeout}s") from exc
            delay = _delay(attempt, policy, None, rng)
            _logger.warning(
                f"{event}.retry", attempt=attempt + 1, reason="timeout", delay_s=round(delay, 3)
            )
            await sleep(delay)
        except Exception as exc:
            if not is_transient(exc) or attempt >= policy.max_retries:
                raise
            delay = _delay(attempt, policy, retry_after_seconds(exc), rng)
            _logger.warning(
                f"{event}.retry",
                attempt=attempt + 1,
                reason=type(exc).__name__,
                delay_s=round(delay, 3),
            )
            await sleep(delay)

    raise LLMError(f"{event} exhausted retries")  # pragma: no cover - loop always returns/raises
