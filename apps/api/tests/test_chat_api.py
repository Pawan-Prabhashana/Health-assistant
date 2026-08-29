"""Chat endpoints: sync turn, persistence, memory, and the five-way fan-out."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry
from sahana_api.models.enums import PatientStatus
from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.patients import PatientRepository
from sahana_api.repositories.sessions import SessionRepository
from tests.conftest import ChatClientFactory

pytestmark = pytest.mark.pg

_IN_SCOPE = {"in_scope": True, "category": "logistics", "reason": "hospital"}
_OFF_TOPIC = {"in_scope": False, "category": "off_topic", "reason": "general"}


def _models(
    *, guardrail: dict[str, Any] = _IN_SCOPE, route: str = "direct", synth_text: str = "Answer."
) -> ModelRegistry:
    return ModelRegistry(
        {
            "guardrail": FakeChatModel(
                role="guardrail",
                structured_by_schema={
                    "GuardrailVerdict": guardrail,
                    "RelevanceGrades": {"grades": [{"index": 0, "relevant": True}]},
                },
            ),
            "router": FakeChatModel(
                role="router",
                structured_payload={
                    "route": route,
                    "confidence": 0.9,
                    "reason": "r",
                    "needs_patient_identity": route == "crm",
                },
            ),
            "synth": FakeChatModel(role="synth", text=synth_text),
        }
    )


def _phone() -> str:
    return f"+9477{uuid.uuid4().int % 10_000_000:07d}"


async def _new_session(db_session: AsyncSession, patient_id: uuid.UUID | None = None) -> uuid.UUID:
    thread = await SessionRepository(db_session).create(patient_id, "Chat")
    await db_session.flush()
    return thread.id


async def test_chat_direct_route_persists_with_metadata(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="direct", synth_text="Hello, welcome!")) as client:
        response = await client.post(
            "/chat", json={"session_id": str(session_id), "message": "Hey there."}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "direct"
    assert body["answer"] == "Hello, welcome!"
    assert body["latency_ms"] >= 0.0

    messages = await MessageRepository(db_session).list_for_session(session_id)
    assert [m.role.value for m in messages] == ["user", "assistant"]
    assert messages[0].content == "Hey there."
    assert messages[1].content == "Hello, welcome!"
    assert messages[1].meta["route"] == "direct"
    assert messages[1].meta["verdict"] == "proceed"
    assert "latency_ms" in messages[1].meta
    assert "usage" in messages[1].meta


async def test_chat_unknown_session_is_404(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    async with build_chat_client(_models()) as client:
        response = await client.post(
            "/chat", json={"session_id": str(uuid.uuid4()), "message": "hi"}
        )
    assert response.status_code == 404


async def test_chat_crm_identified_returns_table(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    phone = _phone()
    patient, _ = await PatientRepository(db_session).upsert_by_phone(phone, "Ada Lovelace")
    patient.status = PatientStatus.ADMITTED
    await AppointmentRepository(db_session).add(
        patient.id, "Cardiology", datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=3)
    )
    session_id = await _new_session(db_session)

    async with build_chat_client(_models(route="crm")) as client:
        response = await client.post(
            "/chat",
            json={
                "session_id": str(session_id),
                "message": "Do I have an appointment?",
                "phone": phone,
            },
        )

    body = response.json()
    assert body["route"] == "crm"
    assert body["structured"] is not None
    assert body["structured"]["columns"] == ["Patient ID", "Name", "Status", "Next Appt"]
    assert body["structured"]["rows"][0][1] == "Ada Lovelace"
    assert "Cardiology" in body["structured"]["rows"][0][3]


async def test_chat_crm_unidentified_asks_to_identify(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="crm")) as client:
        response = await client.post(
            "/chat", json={"session_id": str(session_id), "message": "My appointment?"}
        )
    body = response.json()
    assert body["route"] == "crm"
    assert body["structured"] is None
    assert "identify" in body["answer"].lower()


async def test_chat_five_way_fan_out_populates_context_nodes(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="direct")) as client:
        response = await client.post(
            "/chat", json={"session_id": str(session_id), "message": "hello"}
        )
    nodes = {entry["node"] for entry in response.json()["trace"]}
    assert {"guardrail", "router", "cag", "patient_lookup", "memory_recall", "decide"} <= nodes


async def test_chat_recall_feeds_prior_turns_to_synth(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    models = _models(route="direct", synth_text="Reply.")
    async with build_chat_client(models) as client:
        await client.post(
            "/chat", json={"session_id": str(session_id), "message": "First question"}
        )
        await client.post(
            "/chat", json={"session_id": str(session_id), "message": "Second question"}
        )

    synth = models.get_model("synth")
    assert isinstance(synth, FakeChatModel)
    second_call = synth.complete_calls[1]
    contents = [message.content for message in second_call]
    assert "First question" in contents  # recalled prior user turn


async def test_chat_refusal_persists_and_no_tool(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(guardrail=_OFF_TOPIC, route="direct")) as client:
        response = await client.post(
            "/chat", json={"session_id": str(session_id), "message": "Weather in Paris?"}
        )
    body = response.json()
    assert body["verdict"] == "out_of_scope"
    assert body["route"] is None
    messages = await MessageRepository(db_session).list_for_session(session_id)
    assert messages[1].meta["verdict"] == "out_of_scope"


async def test_history_pagination(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    async with build_chat_client(_models(route="direct")) as client:
        for i in range(3):
            await client.post("/chat", json={"session_id": str(session_id), "message": f"q{i}"})
        history = await client.get(
            "/chat/history", params={"session_id": str(session_id), "limit": 2}
        )

    body = history.json()
    assert body["total"] == 6  # 3 turns, user + assistant each
    assert len(body["messages"]) == 2
    assert body["messages"][0]["content"] == "q0"
    assert "metadata" in body["messages"][0]


async def test_summarize_then_clear_memory(
    build_chat_client: ChatClientFactory, db_session: AsyncSession
) -> None:
    session_id = await _new_session(db_session)
    models = _models(route="direct")
    async with build_chat_client(models) as client:
        for i in range(4):
            await client.post("/chat", json={"session_id": str(session_id), "message": f"turn {i}"})

        summarize = await client.post("/chat/summarize", params={"session_id": str(session_id)})
        assert summarize.status_code == 200
        assert summarize.json()["updated"] is True

        thread = await SessionRepository(db_session).get_by_id(session_id)
        assert thread is not None and thread.summary is not None

        cleared = await client.delete("/chat/memory", params={"session_id": str(session_id)})
        assert cleared.status_code == 204

    refreshed = await SessionRepository(db_session).get_by_id(session_id)
    assert refreshed is not None
    assert refreshed.summary is None
    assert await MessageRepository(db_session).count_for_session(session_id) == 0
