"""CRM tool: identity gate, own-data-only, deterministic rendering (real Postgres)."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import RequestContext
from sahana_api.graph.tools import ToolRequest
from sahana_api.models.enums import PatientStatus
from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.patients import PatientRepository
from sahana_api.tools.crm import CrmTool
from sahana_api.tools.prompts import IDENTIFY_REQUIRED

pytestmark = pytest.mark.pg

UTC = datetime.UTC


def _phone() -> str:
    suffix = uuid.uuid4().int % 10_000_000
    return f"+9477{suffix:07d}"


def _provider(session: AsyncSession) -> CrmTool:
    @asynccontextmanager
    async def _session() -> AsyncIterator[AsyncSession]:
        yield session

    return CrmTool(_session)


async def test_identified_patient_returns_own_structured_table(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    appointments = AppointmentRepository(db_session)
    patient, _ = await patients.upsert_by_phone(_phone(), "Ada Lovelace")
    patient.status = PatientStatus.ADMITTED
    when = datetime.datetime.now(UTC) + datetime.timedelta(days=5)
    await appointments.add(patient.id, "Cardiology", when)
    await db_session.flush()

    result = await _provider(db_session).run(
        ToolRequest("Do I have an appointment today?", RequestContext(patient_id=patient.id))
    )

    assert result.route is Route.CRM
    assert result.metadata["status"] == "crm_ok"
    assert result.structured is not None
    assert result.structured.columns == ["Patient ID", "Name", "Status", "Next Appt"]
    row = result.structured.rows[0]
    assert row[0] == patient.mrn
    assert row[1] == "Ada Lovelace"
    assert row[2] == PatientStatus.ADMITTED.value
    assert "Cardiology" in row[3]
    assert when.strftime("%Y-%m-%d") in row[3]
    for cell in row:
        assert cell in result.payload


async def test_unidentified_caller_gets_identify_first_and_no_data(
    db_session: AsyncSession,
) -> None:
    result = await _provider(db_session).run(
        ToolRequest("Do I have an appointment today?", RequestContext())
    )

    assert result.metadata["status"] == "identify_required"
    assert result.payload == IDENTIFY_REQUIRED
    assert result.structured is None
    assert result.citations == []


async def test_cannot_return_another_patients_rows(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    appointments = AppointmentRepository(db_session)
    owner, _ = await patients.upsert_by_phone(_phone(), "Owner Patient")
    other, _ = await patients.upsert_by_phone(_phone(), "Other Patient")
    await appointments.add(
        other.id, "Secret Ward", datetime.datetime.now(UTC) + datetime.timedelta(days=1)
    )
    await db_session.flush()

    result = await _provider(db_session).run(
        ToolRequest("Show my records", RequestContext(patient_id=owner.id))
    )

    assert result.structured is not None
    serialized = " ".join(result.structured.rows[0]) + " " + result.payload
    assert "Owner Patient" in serialized
    assert "Other Patient" not in serialized
    assert "Secret Ward" not in serialized
    assert other.mrn not in serialized


async def test_unknown_patient_id_is_identify_first(db_session: AsyncSession) -> None:
    result = await _provider(db_session).run(
        ToolRequest("My appointment?", RequestContext(patient_id=uuid.uuid4()))
    )
    assert result.metadata["status"] == "identify_required"
    assert result.structured is None


async def test_no_database_does_not_invent_records() -> None:
    result = await CrmTool(None).run(
        ToolRequest("My appointment?", RequestContext(patient_id=uuid.uuid4()))
    )
    assert result.structured is None
    assert result.metadata["status"] == "unavailable"
