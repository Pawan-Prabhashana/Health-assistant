"""Core LLM types and the ``ChatModel`` abstraction.

A ``ChatModel`` is the transport-agnostic contract the decision graph (Phase 4)
and the chat pipeline (Phase 6) sit on. Three roles — guardrail, router, synth —
are exposed through a registry so callers ask for a role, not a vendor.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

Role = Literal["guardrail", "router", "synth"]
MessageRole = Literal["system", "user", "assistant"]


class LLMError(RuntimeError):
    """Base class for all LLM transport errors."""


class LLMTimeoutError(LLMError):
    """Raised when a call exceeds the per-attempt timeout and retries are exhausted."""


class LLMResponseError(LLMError):
    """Raised when a provider returns an unusable response (e.g. empty content)."""


class StructuredParseError(LLMError):
    """Raised when a structured response cannot be validated after repair attempts."""


class ProviderNotConfiguredError(LLMError):
    """Raised when a role is requested that has no configured model."""


@dataclass(frozen=True)
class Message:
    """A single chat message."""

    role: MessageRole
    content: str


@dataclass(frozen=True)
class Usage:
    """Token, cost, and latency accounting for one completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: float


@dataclass(frozen=True)
class Completion:
    """A text completion with its usage record."""

    text: str
    model: str
    finish_reason: str | None
    usage: Usage


@dataclass(frozen=True)
class StructuredCompletion[T: BaseModel]:
    """A schema-validated completion carrying the parsed model and raw text."""

    value: T
    raw_text: str
    model: str
    usage: Usage


@dataclass(frozen=True)
class TextDelta:
    """An incremental text chunk from a streaming completion."""

    text: str


@dataclass(frozen=True)
class StreamCompleted:
    """The terminal event of a stream, carrying usage when the provider reports it."""

    usage: Usage | None


type StreamEvent = TextDelta | StreamCompleted


class ChatModel(ABC):
    """Transport-agnostic chat model for one configured (provider, model) pair."""

    @property
    @abstractmethod
    def model(self) -> str:
        """The configured model identifier."""

    @abstractmethod
    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> Completion:
        """Return a text completion for ``messages``."""

    @abstractmethod
    async def complete_structured[T: BaseModel](
        self,
        messages: Sequence[Message],
        schema: type[T],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> StructuredCompletion[T]:
        """Return a response validated into ``schema``, repairing malformed JSON once."""

    @abstractmethod
    def stream_events(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Yield text deltas then a terminal :class:`StreamCompleted` carrying usage."""

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas for ``messages`` (provider-agnostic), dropping usage."""
        async for event in self.stream_events(
            messages, temperature=temperature, max_tokens=max_tokens
        ):
            if isinstance(event, TextDelta):
                yield event.text
