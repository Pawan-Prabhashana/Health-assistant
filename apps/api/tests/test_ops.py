"""Operational-layer tests (Phase 9): correlation ids, metrics, input bounds,
and the rate limiter. These run in the fast tier — no database, no keys."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from starlette.requests import Request

from sahana_api.metrics import record_turn
from sahana_api.ratelimit import RateLimiter, RateLimitExceededError
from sahana_api.schemas.chat import ChatRequest


def _fake_request(ip: str = "1.2.3.4") -> Request:
    scope = {"type": "http", "headers": [], "client": (ip, 0), "method": "POST", "path": "/"}
    return Request(scope)


async def test_correlation_id_generated_and_returned(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


async def test_correlation_id_echoed_when_supplied(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "trace-abc-123"})
    assert response.headers.get("X-Request-ID") == "trace-abc-123"


async def test_metrics_endpoint_exposes_recorded_series(client: AsyncClient) -> None:
    record_turn("rag", "proceed", 1700.0)
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "sahana_chat_turns_total" in body
    assert "sahana_chat_turn_latency_seconds" in body
    assert "sahana_chat_cache_total" in body


async def test_body_size_limit_rejects_oversized_request(client: AsyncClient) -> None:
    # A body beyond the 65536-byte cap is rejected with 413 before routing or
    # body validation (the oversized payload never reaches the model path).
    huge = "x" * 70000
    response = await client.post("/chat", json={"session_id": str(uuid.uuid4()), "message": huge})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_chat_request_rejects_overlong_message() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(session_id=uuid.uuid4(), message="x" * 5000)


async def test_rate_limiter_blocks_after_limit_with_retry_after() -> None:
    limiter = RateLimiter(limit="2/minute", enabled=True)
    request = _fake_request()
    await limiter.enforce(request, None)
    await limiter.enforce(request, None)
    with pytest.raises(RateLimitExceededError) as exc:
        await limiter.enforce(request, None)
    assert exc.value.retry_after >= 1


async def test_rate_limiter_disabled_is_noop() -> None:
    limiter = RateLimiter(limit="1/minute", enabled=False)
    request = _fake_request()
    for _ in range(5):
        await limiter.enforce(request, None)


async def test_rate_limiter_keys_identities_separately() -> None:
    limiter = RateLimiter(limit="1/minute", enabled=True)
    request = _fake_request()
    await limiter.enforce(request, "+94771234567")
    # A different identity has its own budget.
    await limiter.enforce(request, "+94770000000")
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce(request, "+94771234567")
