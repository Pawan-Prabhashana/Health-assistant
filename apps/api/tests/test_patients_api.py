"""Endpoint tests for the patient API."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.pg

PATIENT_KEYS = {"id", "mrn", "phone", "full_name", "status", "created_at"}


async def test_create_patient_normalizes_phone(pg_client: AsyncClient) -> None:
    response = await pg_client.post("/patients", json={"phone": "0771234567", "full_name": "Jo"})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == PATIENT_KEYS
    assert body["phone"] == "+94771234567"
    assert body["full_name"] == "Jo"
    assert body["mrn"].startswith("P-")
    assert body["status"] == "stable"


async def test_upsert_is_idempotent(pg_client: AsyncClient) -> None:
    first = await pg_client.post("/patients", json={"phone": "+94772345678", "full_name": "A"})
    assert first.status_code == 201
    created = first.json()

    second = await pg_client.post("/patients", json={"phone": "0772345678", "full_name": "B"})
    assert second.status_code == 200
    updated = second.json()

    assert updated["id"] == created["id"]
    assert updated["mrn"] == created["mrn"]
    assert updated["full_name"] == "B"


async def test_get_patient_by_id(pg_client: AsyncClient) -> None:
    created = (
        await pg_client.post("/patients", json={"phone": "+94711234567", "full_name": "Nimal"})
    ).json()

    found = await pg_client.get(f"/patients/{created['id']}")
    assert found.status_code == 200
    assert found.json()["id"] == created["id"]

    missing = await pg_client.get(f"/patients/{uuid.uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_get_patient_by_phone(pg_client: AsyncClient) -> None:
    await pg_client.post("/patients", json={"phone": "+94761234567", "full_name": "Kamala"})

    found = await pg_client.get("/patients/by-phone/0761234567")
    assert found.status_code == 200
    assert found.json()["phone"] == "+94761234567"

    missing = await pg_client.get("/patients/by-phone/+94701234567")
    assert missing.status_code == 404


async def test_get_patient_by_invalid_phone_is_422(pg_client: AsyncClient) -> None:
    response = await pg_client.get("/patients/by-phone/not-a-number")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_invalid_phone_error_does_not_echo_input(pg_client: AsyncClient) -> None:
    response = await pg_client.post("/patients", json={"phone": "12", "full_name": "x"})
    assert response.status_code == 422
    assert "12" not in response.text or "code" in response.json()["error"]


async def test_delete_patient_returns_204_then_404(pg_client: AsyncClient) -> None:
    created = (
        await pg_client.post("/patients", json={"phone": "+94751234567", "full_name": "Sunil"})
    ).json()

    deleted = await pg_client.delete(f"/patients/{created['id']}")
    assert deleted.status_code == 204

    assert (await pg_client.get(f"/patients/{created['id']}")).status_code == 404
    assert (await pg_client.delete(f"/patients/{created['id']}")).status_code == 404


async def test_delete_patient_cascades_sessions(pg_client: AsyncClient) -> None:
    phone = "+94781234567"
    patient = (await pg_client.post("/patients", json={"phone": phone, "full_name": "Ravi"})).json()
    session = (await pg_client.post("/sessions", json={"phone": phone, "title": "T"})).json()

    assert session["patient_id"] == patient["id"]

    await pg_client.delete(f"/patients/{patient['id']}")

    assert (await pg_client.get(f"/sessions/{session['id']}")).status_code == 404
