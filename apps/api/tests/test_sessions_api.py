"""Endpoint tests for the session API."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.pg

SESSION_KEYS = {"id", "patient_id", "title", "created_at", "updated_at"}


async def test_create_session_without_phone_is_anonymous(pg_client: AsyncClient) -> None:
    response = await pg_client.post("/sessions", json={})

    assert response.status_code == 201
    body = response.json()
    assert body["patient_id"] is None
    assert body["title"] == "New conversation"


async def test_create_session_associates_known_patient(pg_client: AsyncClient) -> None:
    phone = "+94771111111"
    patient = (await pg_client.post("/patients", json={"phone": phone, "full_name": "Ivy"})).json()

    session = await pg_client.post("/sessions", json={"phone": phone, "title": "Hello"})
    assert session.status_code == 201
    assert session.json()["patient_id"] == patient["id"]


async def test_create_session_with_unknown_phone_is_unassociated(pg_client: AsyncClient) -> None:
    session = await pg_client.post("/sessions", json={"phone": "+94772222222"})
    assert session.status_code == 201
    assert session.json()["patient_id"] is None


async def test_list_sessions_requires_a_filter(pg_client: AsyncClient) -> None:
    response = await pg_client.get("/sessions")
    assert response.status_code == 422


async def test_list_sessions_by_phone_newest_first_and_no_pii(pg_client: AsyncClient) -> None:
    phone = "+94773333333"
    await pg_client.post("/patients", json={"phone": phone, "full_name": "Secret Name"})
    await pg_client.post("/sessions", json={"phone": phone, "title": "First"})
    await pg_client.post("/sessions", json={"phone": phone, "title": "Second"})

    response = await pg_client.get("/sessions", params={"phone": phone})
    assert response.status_code == 200
    items = response.json()
    assert [item["title"] for item in items] == ["Second", "First"]

    # List responses must never carry patient PII.
    for item in items:
        assert set(item) == SESSION_KEYS
    assert "Secret Name" not in response.text
    assert phone not in response.text


async def test_list_sessions_unknown_phone_is_empty(pg_client: AsyncClient) -> None:
    response = await pg_client.get("/sessions", params={"phone": "+94774444444"})
    assert response.status_code == 200
    assert response.json() == []


async def test_list_sessions_respects_limit_bounds(pg_client: AsyncClient) -> None:
    response = await pg_client.get("/sessions", params={"phone": "+94775555555", "limit": 0})
    assert response.status_code == 422


async def test_get_session_include_messages(pg_client: AsyncClient) -> None:
    created = (await pg_client.post("/sessions", json={"title": "Thread"})).json()

    plain = await pg_client.get(f"/sessions/{created['id']}")
    assert plain.status_code == 200
    assert plain.json()["messages"] is None

    with_messages = await pg_client.get(
        f"/sessions/{created['id']}", params={"include": "messages"}
    )
    assert with_messages.status_code == 200
    assert with_messages.json()["messages"] == []


async def test_get_session_not_found(pg_client: AsyncClient) -> None:
    response = await pg_client.get(f"/sessions/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_delete_session_returns_204_then_404(pg_client: AsyncClient) -> None:
    created = (await pg_client.post("/sessions", json={"title": "Thread"})).json()

    assert (await pg_client.delete(f"/sessions/{created['id']}")).status_code == 204
    assert (await pg_client.get(f"/sessions/{created['id']}")).status_code == 404
    assert (await pg_client.delete(f"/sessions/{created['id']}")).status_code == 404
