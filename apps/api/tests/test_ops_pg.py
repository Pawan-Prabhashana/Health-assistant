"""Operational-layer tests needing Postgres (Phase 9): auto-summarization closes
the mid-conversation memory gap, the per-patient session cap, and the rate-limit
429 end to end through the chat endpoint."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry
from sahana_api.memory.recall import recall
from sahana_api.memory.summarize import maybe_refresh_summary
from sahana_api.models.enums import MessageRole
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.sessions import SessionRepository
from tests.conftest import ChatClientFactory

pytestmark = pytest.mark.pg

_IN_SCOPE = {"in_scope": True, "category": "logistics", "reason": "hospital"}


def _models(*, route: str = "direct", synth_text: str = "Answer.") -> ModelRegistry:
    return ModelRegistry(
        {
            "guardrail": FakeChatModel(
                role="guardrail",
                structured_by_schema={"GuardrailVerdict": _IN_SCOPE},
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
            "synth": FakeChatModel(role="synth", text=synth_text),
        }
    )


def _phone() -> str:
    return f"+9477{uuid.uuid4().int % 10_000_000:07d}"


async def test_auto_summary_refreshes_past_threshold_and_closes_gap(
    db_session: AsyncSession, session_provider: Callable[[], Any]
) -> None:
    thread = await SessionRepository(db_session).create(None, "Chat")
    await db_session.flush()
    repo = MessageRepository(db_session)
    # Six messages (three turns); the first carries a fact that will fall outside
    # the last-2 recall window as the thread grows.
    contents = [
        "my name is Alex",
        "hello Alex",
        "what are visiting hours",
        "ten to eight",
        "is there parking",
        "yes, on level 2",
    ]
    for index, content in enumerate(contents):
        role = MessageRole.USER if index % 2 == 0 else MessageRole.ASSISTANT
        await repo.add(thread.id, role, content)
    await db_session.flush()

    summary_model = FakeChatModel(role="guardrail", text="Running summary: caller is Alex.")

    # Below the threshold nothing is summarized.
    assert (
        await maybe_refresh_summary(
            db_session, summary_model, thread.id, threshold=100, keep_recent=2
        )
        is None
    )

    # Past the threshold the rolling summary is refreshed without a manual call.
    refreshed = await maybe_refresh_summary(
        db_session, summary_model, thread.id, threshold=4, keep_recent=2
    )
    assert refreshed == "Running summary: caller is Alex."
    await db_session.flush()

    # Recall now returns the summary plus only the last two turns; the dropped
    # middle turn ("my name is Alex") survives via the summary, not the window.
    memory = await recall(session_provider, thread.id, recall_turns=2)
    assert memory.summary == "Running summary: caller is Alex."
    assert len(memory.turns) == 2
    assert all("my name is Alex" not in turn.content for turn in memory.turns)


async def test_session_cap_rejects_over_limit(
    build_chat_client: ChatClientFactory,
) -> None:
    phone = _phone()
    async with build_chat_client(_models(), max_sessions_per_patient=1) as client:
        created = await client.post("/patients", json={"phone": phone})
        assert created.status_code == 201
        first = await client.post("/sessions", json={"phone": phone})
        assert first.status_code == 201
        second = await client.post("/sessions", json={"phone": phone})
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "session_limit_reached"


async def test_chat_rate_limit_returns_429_with_retry_after(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    thread = await SessionRepository(db_session).create(None, "Chat")
    await db_session.flush()
    async with build_chat_client(_models(synth_text="Hi."), rate_limit="1/minute") as client:
        first = await client.post("/chat", json={"session_id": str(thread.id), "message": "Hello."})
        assert first.status_code == 200
        second = await client.post(
            "/chat", json={"session_id": str(thread.id), "message": "Hello again."}
        )
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "rate_limited"
        assert int(second.headers["Retry-After"]) >= 1
