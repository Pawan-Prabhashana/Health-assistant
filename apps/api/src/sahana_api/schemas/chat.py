"""Chat request/response schemas and the SSE event serialization.

The sync and streaming endpoints share one response shape: ``ChatResponse`` is the
body of ``POST /chat`` and the payload of the SSE ``final`` event, so the Phase 7
frontend consumes one schema for both.
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from sahana_api.graph.pipeline import (
    DeltaEvent,
    FinalEvent,
    PipelineEvent,
    PipelineResult,
    RoutingEvent,
)


class ChatRequest(BaseModel):
    """Body for ``POST /chat`` and ``POST /chat/stream``."""

    session_id: uuid.UUID
    message: str = Field(min_length=1, max_length=4000)
    phone: str | None = Field(default=None, description="Caller phone; resolved to identity.")


class UsageResponse(BaseModel):
    """Token, cost, and latency accounting for the synth call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    latency_ms: float


class TableResponse(BaseModel):
    """A structured table (the CRM reply) for the frontend to render verbatim."""

    columns: list[str]
    rows: list[list[str]]


class TraceEntryResponse(BaseModel):
    """One node's PII-free trace contribution."""

    node: str
    data: dict[str, Any]


class ChatResponse(BaseModel):
    """The structured result of one chat turn."""

    verdict: str
    route: str | None
    answer: str
    citations: list[str]
    structured: TableResponse | None
    usage: UsageResponse | None
    latency_ms: float
    trace: list[TraceEntryResponse]

    @classmethod
    def from_result(cls, result: PipelineResult) -> ChatResponse:
        """Build the response from a :class:`PipelineResult`."""
        return cls(
            verdict=result.verdict.value,
            route=result.route.value if result.route is not None else None,
            answer=result.answer,
            citations=result.citations,
            structured=(
                TableResponse(columns=result.structured.columns, rows=result.structured.rows)
                if result.structured is not None
                else None
            ),
            usage=(
                UsageResponse(
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    total_tokens=result.usage.total_tokens,
                    estimated_cost_usd=result.usage.estimated_cost_usd,
                    latency_ms=result.usage.latency_ms,
                )
                if result.usage is not None
                else None
            ),
            latency_ms=result.latency_ms,
            trace=[TraceEntryResponse(node=entry.node, data=entry.data) for entry in result.trace],
        )


class ChatMessageResponse(BaseModel):
    """A persisted message in the history read."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    metadata: dict[str, Any] = Field(validation_alias="meta", serialization_alias="metadata")
    created_at: datetime.datetime


class ChatHistoryResponse(BaseModel):
    """Paginated message history for a session, oldest first."""

    session_id: uuid.UUID
    total: int
    messages: list[ChatMessageResponse]


class SummarizeResponse(BaseModel):
    """The result of refreshing a session's rolling summary."""

    session_id: uuid.UUID
    summary: str | None
    updated: bool


def format_sse(event: PipelineEvent) -> str:
    """Serialize a pipeline event as an SSE ``event:``/``data:`` frame."""
    if isinstance(event, RoutingEvent):
        data = {"verdict": event.verdict.value, "route": event.route.value if event.route else None}
        return _frame("routing", data)
    if isinstance(event, DeltaEvent):
        return _frame("delta", {"text": event.text})
    if isinstance(event, FinalEvent):
        return _frame_json("final", ChatResponse.from_result(event.result).model_dump_json())
    return _frame("error", {"code": event.code, "message": event.message})


def _frame(name: str, data: dict[str, Any]) -> str:
    return _frame_json(name, json.dumps(data))


def _frame_json(name: str, payload: str) -> str:
    return f"event: {name}\ndata: {payload}\n\n"
