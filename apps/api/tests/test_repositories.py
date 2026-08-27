"""Repository tests against a real Postgres."""

from __future__ import annotations

import datetime
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.models.appointment import Appointment
from sahana_api.models.enums import AppointmentStatus, MessageRole, PatientStatus
from sahana_api.models.session import DEFAULT_SESSION_TITLE, Session
from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.patients import DEFAULT_PATIENT_NAME, PatientRepository
from sahana_api.repositories.sessions import SessionRepository

pytestmark = pytest.mark.pg

UTC = datetime.UTC


def _unique_phone() -> str:
    """Return a distinct valid Sri Lankan mobile number for isolation."""
    suffix = uuid.uuid4().int % 10_000_000
    return f"+9477{suffix:07d}"


async def test_patient_upsert_creates_then_updates(db_session: AsyncSession) -> None:
    repo = PatientRepository(db_session)
    phone = _unique_phone()

    patient, created = await repo.upsert_by_phone(phone, "Ada Lovelace")
    assert created is True
    assert patient.phone == phone
    assert patient.full_name == "Ada Lovelace"
    assert patient.mrn.startswith("P-")
    assert patient.status is PatientStatus.STABLE

    same, created_again = await repo.upsert_by_phone(phone, "Ada L.")
    assert created_again is False
    assert same.id == patient.id
    assert same.full_name == "Ada L."
    assert same.mrn == patient.mrn


async def test_patient_upsert_without_name_uses_default(db_session: AsyncSession) -> None:
    repo = PatientRepository(db_session)
    patient, created = await repo.upsert_by_phone(_unique_phone(), None)
    assert created is True
    assert patient.full_name == DEFAULT_PATIENT_NAME


async def test_patient_lookup_helpers(db_session: AsyncSession) -> None:
    repo = PatientRepository(db_session)
    phone = _unique_phone()
    created, _ = await repo.upsert_by_phone(phone, "Grace Hopper")

    assert (await repo.get_by_id(created.id)) is not None
    assert (await repo.get_by_phone(phone)) is not None
    assert (await repo.get_by_id(uuid.uuid4())) is None
    assert (await repo.get_by_phone(_unique_phone())) is None


async def test_patient_delete_cascades(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    appointments = AppointmentRepository(db_session)
    sessions = SessionRepository(db_session)
    messages = MessageRepository(db_session)

    patient, _ = await patients.upsert_by_phone(_unique_phone(), "Alan Turing")
    await appointments.add(patient.id, "Neurology", datetime.datetime.now(UTC))
    thread = await sessions.create(patient.id, "Thread")
    await messages.add(thread.id, MessageRole.USER, "hello")

    deleted = await patients.delete_by_id(patient.id)
    assert deleted is True
    assert (await patients.get_by_id(patient.id)) is None

    appt_count = await db_session.scalar(
        select(func.count()).select_from(Appointment).where(Appointment.patient_id == patient.id)
    )
    session_count = await db_session.scalar(
        select(func.count()).select_from(Session).where(Session.patient_id == patient.id)
    )
    assert appt_count == 0
    assert session_count == 0

    assert (await patients.delete_by_id(uuid.uuid4())) is False


async def test_session_repository_crud(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    sessions = SessionRepository(db_session)
    patient, _ = await patients.upsert_by_phone(_unique_phone(), "Katherine Johnson")

    anonymous = await sessions.create(None, None)
    assert anonymous.patient_id is None
    assert anonymous.title == DEFAULT_SESSION_TITLE

    first = await sessions.create(patient.id, "First")
    second = await sessions.create(patient.id, "Second")

    listed = await sessions.list_for_patient(patient.id, limit=10, offset=0)
    assert [thread.id for thread in listed] == [second.id, first.id]

    page = await sessions.list_for_patient(patient.id, limit=1, offset=1)
    assert [thread.id for thread in page] == [first.id]

    assert (await sessions.get_by_id(first.id)) is not None
    assert (await sessions.delete_by_id(first.id)) is True
    assert (await sessions.get_by_id(first.id)) is None
    assert (await sessions.delete_by_id(uuid.uuid4())) is False


async def test_message_repository_orders_and_defaults(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    sessions = SessionRepository(db_session)
    messages = MessageRepository(db_session)
    patient, _ = await patients.upsert_by_phone(_unique_phone(), "Margaret Hamilton")
    thread = await sessions.create(patient.id, "Thread")

    first = await messages.add(thread.id, MessageRole.USER, "hi")
    await messages.add(thread.id, MessageRole.ASSISTANT, "hello", {"route": "concierge"})

    assert first.meta == {}
    listed = await messages.list_for_session(thread.id)
    assert [message.content for message in listed] == ["hi", "hello"]
    assert listed[1].meta == {"route": "concierge"}


async def test_appointment_next_upcoming(db_session: AsyncSession) -> None:
    patients = PatientRepository(db_session)
    appointments = AppointmentRepository(db_session)
    patient, _ = await patients.upsert_by_phone(_unique_phone(), "Radia Perlman")
    now = datetime.datetime.now(UTC)

    await appointments.add(
        patient.id,
        "Cardiology",
        now - datetime.timedelta(days=1),
        status=AppointmentStatus.COMPLETED,
    )
    soon = await appointments.add(patient.id, "Dermatology", now + datetime.timedelta(days=2))
    await appointments.add(patient.id, "Orthopedics", now + datetime.timedelta(days=9))
    await appointments.add(
        patient.id,
        "Neurology",
        now + datetime.timedelta(days=1),
        status=AppointmentStatus.CANCELLED,
    )

    upcoming = await appointments.next_upcoming_for_patient(patient.id, now=now)
    assert upcoming is not None
    assert upcoming.id == soon.id

    listed = await appointments.list_for_patient(patient.id)
    assert len(listed) == 4
