"""Chat endpoints: sync, streaming (SSE), history, summarize, and clear-memory."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.cag.cache import CagCache
from sahana_api.chat.service import persist_turn, schedule_cache_side_effects, stream_chat
from sahana_api.config import Settings
from sahana_api.db.session import get_session
from sahana_api.errors import NotFoundError, ServiceUnavailableError
from sahana_api.graph.context import RequestContext
from sahana_api.graph.pipeline import CompiledPipeline, run_pipeline
from sahana_api.llm.base import ProviderNotConfiguredError
from sahana_api.llm.registry import ModelRegistry
from sahana_api.memory.recall import SessionProvider
from sahana_api.memory.summarize import summarize_session
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.sessions import SessionRepository
from sahana_api.schemas.chat import (
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatRequest,
    ChatResponse,
    SummarizeResponse,
)
from sahana_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT, ErrorEnvelope

router = APIRouter(prefix="/chat", tags=["chat"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}
}


def _pipeline(request: Request) -> CompiledPipeline:
    pipeline: CompiledPipeline | None = request.app.state.graph
    if pipeline is None:
        raise ServiceUnavailableError("chat pipeline is not configured")
    return pipeline


def _cag(request: Request) -> CagCache | None:
    cag: CagCache | None = request.app.state.cag
    return cag


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _session_provider(request: Request) -> SessionProvider | None:
    database = request.app.state.db
    if database is None:
        return None
    provider: SessionProvider = database.sessionmaker
    return provider


async def _require_session(session: AsyncSession, session_id: uuid.UUID) -> None:
    if await SessionRepository(session).get_by_id(session_id) is None:
        raise NotFoundError("session")


@router.post(
    "",
    response_model=ChatResponse,
    responses=_NOT_FOUND,
    summary="One synchronous chat turn",
)
async def chat(
    payload: ChatRequest, request: Request, session: SessionDep, background: BackgroundTasks
) -> ChatResponse:
    """Run the pipeline, persist the turn, close the CAG loop, and return the result."""
    await _require_session(session, payload.session_id)
    context = RequestContext(session_id=payload.session_id, phone=payload.phone)
    result = await run_pipeline(_pipeline(request), payload.message, context)
    await persist_turn(session, payload.session_id, payload.message, result)
    schedule_cache_side_effects(
        background, _cag(request), _settings(request), payload.message, result
    )
    return ChatResponse.from_result(result)


@router.post("/stream", summary="One chat turn, streamed over SSE")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Stream the same pipeline as ``routing``/``delta``/``final``/``error`` SSE events."""
    provider = _session_provider(request)
    if provider is None:
        raise ServiceUnavailableError("chat streaming requires a database")
    async with provider() as session:
        await _require_session(session, payload.session_id)
    context = RequestContext(session_id=payload.session_id, phone=payload.phone)
    stream = stream_chat(
        pipeline=_pipeline(request),
        session_provider=provider,
        cag=_cag(request),
        settings=_settings(request),
        session_id=payload.session_id,
        message=payload.message,
        context=context,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        # Disable proxy buffering end to end: nginx honours ``X-Accel-Buffering:
        # no`` to flush SSE frames as they are produced rather than at stream end,
        # and ``Cache-Control: no-cache`` keeps intermediaries from caching the
        # event stream. See ADR 0014.
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    responses=_NOT_FOUND,
    summary="Read a session's message history",
)
async def chat_history(
    session: SessionDep,
    session_id: Annotated[uuid.UUID, Query(description="Session to read.")],
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ChatHistoryResponse:
    """Return persisted messages for a session, oldest first, paginated."""
    await _require_session(session, session_id)
    repo = MessageRepository(session)
    total = await repo.count_for_session(session_id)
    messages = await repo.list_for_session(session_id, limit=limit, offset=offset)
    return ChatHistoryResponse(
        session_id=session_id,
        total=total,
        messages=[ChatMessageResponse.model_validate(message) for message in messages],
    )


@router.post(
    "/summarize",
    response_model=SummarizeResponse,
    responses=_NOT_FOUND,
    summary="Refresh a session's rolling summary",
)
async def chat_summarize(
    request: Request,
    session: SessionDep,
    session_id: Annotated[uuid.UUID, Query(description="Session to summarize.")],
) -> SummarizeResponse:
    """Compress the session's older turns into a bounded rolling summary."""
    await _require_session(session, session_id)
    models: ModelRegistry = request.app.state.llm
    try:
        model = models.get_model(_settings(request).summary_model_role)
    except ProviderNotConfiguredError as exc:
        raise ServiceUnavailableError("summary model is not configured") from exc
    summary = await summarize_session(
        session, model, session_id, keep_recent=_settings(request).memory_recall_turns
    )
    return SummarizeResponse(session_id=session_id, summary=summary, updated=summary is not None)


@router.delete(
    "/memory",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="Clear a session's short-term memory",
)
async def chat_clear_memory(
    session: SessionDep,
    session_id: Annotated[uuid.UUID, Query(description="Session to clear.")],
) -> Response:
    """Delete a session's messages and summary, keeping the session record."""
    cleared = await SessionRepository(session).clear_memory(session_id)
    if not cleared:
        raise NotFoundError("session")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
