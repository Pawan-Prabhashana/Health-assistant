"""Tests for the LLM retry/backoff policy (no network)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    BadRequestError,
    InternalServerError,
    RateLimitError,
)

from sahana_api.llm.base import LLMTimeoutError
from sahana_api.llm.retry import (
    RetryPolicy,
    is_transient,
    retry_after_seconds,
    run_with_policy,
)

_REQUEST = httpx.Request("POST", "https://api.example/v1/chat/completions")


def _response(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=_REQUEST)


def _rate_limit(retry_after: str | None) -> RateLimitError:
    headers = {"retry-after": retry_after} if retry_after is not None else {}
    return RateLimitError("rate limited", response=_response(429, headers), body=None)


class _Recorder:
    """Records sleep delays instead of sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def test_is_transient_classification() -> None:
    assert is_transient(APITimeoutError(_REQUEST)) is True
    assert is_transient(APIConnectionError(request=_REQUEST)) is True
    assert is_transient(_rate_limit("1")) is True
    assert is_transient(InternalServerError("boom", response=_response(500), body=None)) is True
    assert is_transient(BadRequestError("bad", response=_response(400), body=None)) is False
    assert is_transient(ValueError("nope")) is False


def test_retry_after_extraction() -> None:
    assert retry_after_seconds(_rate_limit("2.5")) == 2.5
    assert retry_after_seconds(_rate_limit(None)) is None
    assert retry_after_seconds(BadRequestError("x", response=_response(400), body=None)) is None


async def test_transient_failure_then_success() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise APIConnectionError(request=_REQUEST)
        return "ok"

    sleeper = _Recorder()
    result = await run_with_policy(
        operation,
        policy=RetryPolicy(max_retries=2),
        timeout=1.0,
        event="test",
        sleep=sleeper,
        rng=lambda: 0.0,
    )

    assert result == "ok"
    assert calls == 2
    assert len(sleeper.delays) == 1


async def test_429_respects_retry_after() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise _rate_limit("2")
        return "ok"

    sleeper = _Recorder()
    result = await run_with_policy(
        operation,
        policy=RetryPolicy(max_retries=2),
        timeout=1.0,
        event="test",
        sleep=sleeper,
        rng=lambda: 0.9,
    )

    assert result == "ok"
    # Retry-After overrides the computed backoff+jitter.
    assert sleeper.delays == [2.0]


async def test_4xx_does_not_retry() -> None:
    calls = 0

    async def operation() -> str:
        nonlocal calls
        calls += 1
        raise BadRequestError("bad", response=_response(400), body=None)

    sleeper = _Recorder()
    with pytest.raises(BadRequestError):
        await run_with_policy(
            operation,
            policy=RetryPolicy(max_retries=3),
            timeout=1.0,
            event="test",
            sleep=sleeper,
        )

    assert calls == 1
    assert sleeper.delays == []


async def test_timeout_is_enforced_and_raised() -> None:
    async def operation() -> str:
        await asyncio.sleep(1.0)
        return "never"

    sleeper = _Recorder()
    with pytest.raises(LLMTimeoutError):
        await run_with_policy(
            operation,
            policy=RetryPolicy(max_retries=0),
            timeout=0.05,
            event="test",
            sleep=sleeper,
        )
