"""Tests for the deterministic fake chat model (no network, no keys)."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from sahana_api.llm.base import LLMResponseError, Message
from sahana_api.llm.fake import FakeChatModel


class _Decision(BaseModel):
    route: str
    confidence: float


async def test_fake_complete_returns_typed_completion_with_usage() -> None:
    model = FakeChatModel(role="synth", text="hello there", latency_ms=2.5)
    completion = await model.complete([Message("user", "hi")])

    assert completion.text == "hello there"
    assert completion.model == "fake-model"
    assert completion.finish_reason == "stop"
    assert completion.usage.prompt_tokens > 0
    assert completion.usage.completion_tokens > 0
    assert completion.usage.total_tokens == (
        completion.usage.prompt_tokens + completion.usage.completion_tokens
    )
    assert completion.usage.latency_ms == 2.5


async def test_fake_structured_parses_into_schema() -> None:
    model = FakeChatModel(structured_payload={"route": "rag", "confidence": 0.9})
    result = await model.complete_structured([Message("user", "q")], _Decision)

    assert isinstance(result.value, _Decision)
    assert result.value.route == "rag"
    assert result.value.confidence == 0.9
    assert result.usage.total_tokens > 0


async def test_fake_structured_by_schema_selects_payload() -> None:
    class _Grade(BaseModel):
        relevant: bool

    model = FakeChatModel(
        structured_payload={"relevant": False},
        structured_by_schema={"_Grade": {"relevant": True}},
    )
    result = await model.complete_structured([Message("user", "q")], _Grade)
    assert result.value.relevant is True
    assert model.structured_calls[0][0] == "_Grade"


async def test_fake_stream_yields_expected_tokens() -> None:
    model = FakeChatModel(stream_tokens=["a", "b", "c"])
    tokens = [token async for token in model.stream([Message("user", "q")])]
    assert tokens == ["a", "b", "c"]


async def test_fake_injected_failure_then_recovers() -> None:
    model = FakeChatModel(failures=1, failure=LLMResponseError("boom"))

    with pytest.raises(LLMResponseError):
        await model.complete([Message("user", "q")])

    recovered = await model.complete([Message("user", "q")])
    assert recovered.text
