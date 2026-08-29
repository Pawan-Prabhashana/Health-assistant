"""SSE streaming chat: event protocol, persistence, and disconnect safety."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.chat.service import stream_chat
from sahana_api.config import Settings
from sahana_api.graph.context import RequestContext
from sahana_api.graph.pipeline import build_graph
from sahana_api.llm.base import Message, StreamEvent, TextDelta
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.sessions import SessionRepository
from sahana_api.tools.tavily import FakeTavilyClient
from sahana_api.tools.wiring import build_real_deps
from tests.conftest import ChatClientFactory

pytestmark = pytest.mark.pg

_IN_SCOPE = {"in_scope": True, "category": "logistics", "reason": "hospital"}
_OFF_TOPIC = {"in_scope": False, "category": "off_topic", "reason": "general"}


def _models(*, guardrail: dict[str, Any] = _IN_SCOPE, route: str = "direct") -> ModelRegistry:
    return ModelRegistry(
        {
            "guardrail": FakeChatModel(
                role="guardrail", structured_by_schema={"GuardrailVerdict": guardrail}
            ),
            "router": FakeChatModel(
                role="router",
                structured_payload={
                    "route": route,
                    "confidence": 0.9,
                    "reason": "r",
                    "needs_patient_identity": False,
                },
            ),
            "synth": FakeChatModel(role="synth", stream_tokens=["Hello", " there."]),
        }
    )


def _event_names(raw: str) -> list[str]:
    names: list[str] = []
    for block in raw.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("event: "):
                names.append(line.removeprefix("event: "))
    return names


async def _new_session(db_session: AsyncSession) -> uuid.UUID:
    thread = await SessionRepository(db_session).create(None, "Chat")
    await db_session.flush()
    return thread.id


async def _collect(client: AsyncClient, session_id: uuid.UUID, message: str) -> str:
    raw = ""
    async with client.stream(
        "POST", "/chat/stream", json={"session_id": str(session_id), "message": message}
    ) as response:
        assert response.status_code == 200
        async for chunk in response.aiter_text():
            raw += chunk
    return raw


async def test_stream_tool_backed_is_routing_deltas_final(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="direct")) as client:
        raw = await _collect(client, session_id, "Hey there.")

    names = _event_names(raw)
    assert names[0] == "routing"
    assert names[-1] == "final"
    assert "delta" in names


async def test_stream_refusal_is_routing_then_single_final(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(guardrail=_OFF_TOPIC)) as client:
        raw = await _collect(client, session_id, "Weather in Paris?")

    names = _event_names(raw)
    assert names == ["routing", "final"]
    assert "delta" not in names


async def test_stream_persists_after_completion(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="direct")) as client:
        await _collect(client, session_id, "Hey there.")

    messages = await MessageRepository(db_session).list_for_session(session_id)
    assert [m.role.value for m in messages] == ["user", "assistant"]
    assert messages[1].content == "Hello there."
    assert messages[1].meta["incomplete"] is False


class _HangingSynth(FakeChatModel):
    """Streams one delta then hangs, so a mid-stream disconnect is deterministic."""

    async def stream_events(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamEvent]:
        yield TextDelta("partial")
        await asyncio.Event().wait()  # never completes; cancelled on disconnect


async def test_stream_disconnect_persists_incomplete(
    db_session: AsyncSession, session_provider: Any
) -> None:
    # Drive stream_chat directly and abort mid-stream to simulate a client
    # disconnect; the shielded finalize must still persist a marked-incomplete pair.
    session_id = await _new_session(db_session)
    models = _models(route="direct")
    models.models["synth"] = _HangingSynth(role="synth")
    settings = Settings(llm_mode="fake", tavily_mode="fake", kb_embedder="local")
    deps = build_real_deps(
        settings,
        models,
        None,
        session_provider=session_provider,
        retriever=None,
        tavily=FakeTavilyClient(),
    )
    pipeline = build_graph(deps)

    generator = stream_chat(
        pipeline=pipeline,
        session_provider=session_provider,
        cag=None,
        settings=settings,
        session_id=session_id,
        message="Hey there.",
        context=RequestContext(session_id=session_id),
    )
    first = await generator.__anext__()  # routing
    second = await generator.__anext__()  # partial delta
    assert "routing" in first
    assert "delta" in second
    await generator.aclose()  # simulate disconnect before completion

    messages = await MessageRepository(db_session).list_for_session(session_id)
    assert [m.role.value for m in messages] == ["user", "assistant"]
    assert messages[1].meta["incomplete"] is True
    assert messages[1].content == "partial"
