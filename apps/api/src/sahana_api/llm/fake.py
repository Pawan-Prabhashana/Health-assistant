"""Deterministic fake chat model for tests and key-free development.

``FakeChatModel`` implements the same ``ChatModel`` contract with canned outputs:
a fixed completion, a schema-valid structured object, and a fixed token stream.
Injected failures let tests drive the retry/timeout paths without a network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from pydantic import BaseModel

from sahana_api.llm.base import (
    ChatModel,
    Completion,
    LLMResponseError,
    Message,
    Role,
    StructuredCompletion,
    Usage,
)
from sahana_api.llm.usage import log_usage

_DEFAULT_STREAM = ["This ", "is ", "a ", "canned ", "response."]


def _rough_tokens(text: str) -> int:
    """A deterministic, network-free token estimate."""
    return max(1, len(text) // 4)


class FakeChatModel(ChatModel):
    """A deterministic ``ChatModel`` returning canned outputs."""

    def __init__(
        self,
        *,
        role: Role = "synth",
        model: str = "fake-model",
        text: str = "This is a canned Sahana response.",
        structured_payload: dict[str, Any] | None = None,
        stream_tokens: list[str] | None = None,
        latency_ms: float = 1.0,
        failures: int = 0,
        failure: Exception | None = None,
    ) -> None:
        self._role = role
        self._model = model
        self._text = text
        self._structured_payload = structured_payload if structured_payload is not None else {}
        self._stream_tokens = stream_tokens if stream_tokens is not None else list(_DEFAULT_STREAM)
        self._latency_ms = latency_ms
        self._remaining_failures = failures
        self._failure = failure if failure is not None else LLMResponseError("injected failure")

    @property
    def model(self) -> str:
        return self._model

    def _maybe_fail(self) -> None:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise self._failure

    def _usage(self, prompt_tokens: int, completion_tokens: int) -> Usage:
        return Usage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            estimated_cost_usd=0.0,
            latency_ms=self._latency_ms,
        )

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Completion:
        self._maybe_fail()
        prompt_tokens = _rough_tokens("".join(message.content for message in messages))
        usage = self._usage(prompt_tokens, _rough_tokens(self._text))
        log_usage(self._role, self._model, usage)
        return Completion(text=self._text, model=self._model, finish_reason="stop", usage=usage)

    async def complete_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> StructuredCompletion[T]:
        self._maybe_fail()
        value = schema.model_validate(self._structured_payload)
        raw_text = value.model_dump_json()
        prompt_tokens = _rough_tokens("".join(message.content for message in messages))
        usage = self._usage(prompt_tokens, _rough_tokens(raw_text))
        log_usage(self._role, self._model, usage)
        return StructuredCompletion(value=value, raw_text=raw_text, model=self._model, usage=usage)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        self._maybe_fail()
        for token in self._stream_tokens:
            yield token
