"""Chat orchestration: message persistence, the CAG loop, and SSE streaming.

The sync endpoint persists the turn on the request session and schedules the CAG
side effects as FastAPI background tasks (non-blocking). The streaming endpoint
persists after the stream completes using its own session provider, shielded so a
client disconnect never leaves a dangling half-written record.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.graph.context import RequestContext
from sahana_api.graph.pipeline import (
    CompiledPipeline,
    DeltaEvent,
    ErrorEvent,
    FinalEvent,
    PipelineResult,
    stream_pipeline,
)
from sahana_api.graph.schemas import Verdict
from sahana_api.llm.base import ChatModel
from sahana_api.logging import get_logger
from sahana_api.memory.recall import SessionProvider
from sahana_api.memory.summarize import maybe_refresh_summary
from sahana_api.metrics import record_error, record_turn
from sahana_api.models.enums import MessageRole
from sahana_api.repositories.messages import MessageRepository
from sahana_api.schemas.chat import format_sse

_logger = get_logger("sahana_api.chat.service")


def _assistant_metadata(result: PipelineResult | None, *, incomplete: bool) -> dict[str, Any]:
    """Build PII-free per-turn metadata for the persisted assistant message."""
    metadata: dict[str, Any] = {"incomplete": incomplete}
    if result is not None:
        metadata["verdict"] = result.verdict.value
        metadata["route"] = result.route.value if result.route is not None else None
        metadata["latency_ms"] = result.latency_ms
        metadata["citations"] = result.citations
        if result.usage is not None:
            metadata["usage"] = {
                "prompt_tokens": result.usage.prompt_tokens,
                "completion_tokens": result.usage.completion_tokens,
                "total_tokens": result.usage.total_tokens,
                "estimated_cost_usd": result.usage.estimated_cost_usd,
            }
    return metadata


async def persist_turn(
    session: AsyncSession, session_id: uuid.UUID, user_message: str, result: PipelineResult
) -> None:
    """Persist the user and assistant messages for a completed sync turn."""
    repo = MessageRepository(session)
    await repo.add(session_id, MessageRole.USER, user_message)
    await repo.add(
        session_id,
        MessageRole.ASSISTANT,
        result.answer,
        _assistant_metadata(result, incomplete=False),
    )


async def _apply_cache_side_effects(
    cag: CagCache | None, settings: Settings, question: str, result: PipelineResult
) -> None:
    """Record a served cache hit, or store a cacheable answer (route-gated in store)."""
    if cag is None:
        return
    if result.verdict is Verdict.CACHE_HIT:
        await cag.record_hit(question)
    elif (
        result.verdict is Verdict.PROCEED
        and settings.cache_store_enabled
        and result.route is not None
        and result.route.value in settings.cag_cacheable_routes
    ):
        await cag.store(question, result.answer, result.route.value)


def schedule_cache_side_effects(
    background: BackgroundTasks,
    cag: CagCache | None,
    settings: Settings,
    question: str,
    result: PipelineResult,
) -> None:
    """Schedule the CAG side effects to run after the response is sent."""
    background.add_task(_apply_cache_side_effects, cag, settings, question, result)


def record_turn_metrics(result: PipelineResult) -> None:
    """Record per-turn Prometheus metrics for a completed turn."""
    record_turn(
        result.route.value if result.route is not None else None,
        result.verdict.value,
        result.latency_ms,
    )


async def _run_memory_maintenance(
    session_provider: SessionProvider | None,
    summary_model: ChatModel | None,
    settings: Settings,
    session_id: uuid.UUID,
) -> None:
    """Refresh the rolling summary when the thread has grown past the threshold.

    Runs in its own session (after the turn is committed) and is best-effort: a
    summary failure must never break the turn it follows.
    """
    if session_provider is None or summary_model is None:
        return
    try:
        async with session_provider() as session:
            await maybe_refresh_summary(
                session,
                summary_model,
                session_id,
                threshold=settings.memory_summary_threshold,
                keep_recent=settings.memory_recall_turns,
            )
            await session.commit()
    except Exception:
        _logger.exception("memory.summary.failed")


def schedule_memory_maintenance(
    background: BackgroundTasks,
    session_provider: SessionProvider | None,
    summary_model: ChatModel | None,
    settings: Settings,
    session_id: uuid.UUID,
) -> None:
    """Schedule the rolling-summary refresh to run after the response is sent."""
    background.add_task(
        _run_memory_maintenance, session_provider, summary_model, settings, session_id
    )


async def _with_keepalive(source: AsyncIterator[str], interval: float) -> AsyncIterator[str]:
    """Relay SSE frames, injecting a heartbeat comment when the source is idle."""
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for frame in source:
                await queue.put(frame)
        finally:
            await queue.put(None)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=interval)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if frame is None:
                break
            yield frame
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


async def stream_chat(
    *,
    pipeline: CompiledPipeline,
    session_provider: SessionProvider | None,
    cag: CagCache | None,
    settings: Settings,
    session_id: uuid.UUID,
    message: str,
    context: RequestContext,
    summary_model: ChatModel | None = None,
) -> AsyncIterator[str]:
    """Yield SSE frames for a streamed turn, persisting the result even on disconnect."""
    pieces: list[str] = []
    final: PipelineResult | None = None

    async def frames() -> AsyncIterator[str]:
        nonlocal final
        try:
            async for event in stream_pipeline(pipeline, message, context):
                if isinstance(event, DeltaEvent):
                    pieces.append(event.text)
                elif isinstance(event, FinalEvent):
                    final = event.result
                yield format_sse(event)
        except Exception:
            _logger.exception("chat.stream.failed")
            record_error("pipeline_error")
            yield format_sse(
                ErrorEvent(
                    code="pipeline_error",
                    message="Something went wrong answering that. Please try again.",
                )
            )

    try:
        async for frame in _with_keepalive(frames(), settings.sse_keepalive_seconds):
            yield frame
    finally:
        await asyncio.shield(
            _finalize_stream(
                session_provider, cag, settings, session_id, message, pieces, final, summary_model
            )
        )


async def _finalize_stream(
    session_provider: SessionProvider | None,
    cag: CagCache | None,
    settings: Settings,
    session_id: uuid.UUID,
    message: str,
    pieces: list[str],
    final: PipelineResult | None,
    summary_model: ChatModel | None,
) -> None:
    """Persist the turn (partial if disconnected), apply CAG effects, refresh memory."""
    answer = final.answer if final is not None else "".join(pieces)
    metadata = _assistant_metadata(final, incomplete=final is None)
    if session_provider is not None:
        async with session_provider() as session:
            repo = MessageRepository(session)
            await repo.add(session_id, MessageRole.USER, message)
            await repo.add(session_id, MessageRole.ASSISTANT, answer, metadata)
            await session.commit()
    if final is not None:
        await _apply_cache_side_effects(cag, settings, message, final)
        record_turn_metrics(final)
    await _run_memory_maintenance(session_provider, summary_model, settings, session_id)
