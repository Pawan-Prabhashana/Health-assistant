"""Idempotent demo-data seed.

Run with ``python -m sahana_api.seed`` (or ``make seed``). Patients are upserted
by phone and each seeded patient's appointments are replaced on every run, so
seeding any number of times converges to the same rows without duplicates.

The data mirrors the CRM slide (e.g. "John Doe", "Donva J.", all stable) plus a
few extra patients and a mix of past/future appointments so later CRM and demo
flows have material. No secrets or real personal data are seeded.
"""

from __future__ import annotations

import asyncio
import datetime
from dataclasses import dataclass, field

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.config import get_settings
from sahana_api.db.engine import Database
from sahana_api.logging import configure_logging, get_logger
from sahana_api.models.appointment import Appointment
from sahana_api.models.enums import AppointmentStatus
from sahana_api.phone import normalize_phone
from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.patients import PatientRepository

_logger = get_logger("sahana_api.seed")


@dataclass(frozen=True)
class SeedAppointment:
    """An appointment defined relative to seed time."""

    department: str
    offset_days: int
    status: AppointmentStatus
    notes: str | None = None


@dataclass(frozen=True)
class SeedPatient:
    """A patient plus the appointments to (re)create for them."""

    full_name: str
    phone: str
    appointments: list[SeedAppointment] = field(default_factory=list)


# Ordered so a fresh seed assigns the slide's MRNs: John Doe -> P-10023, etc.
SEED_PATIENTS: list[SeedPatient] = [
    SeedPatient(
        full_name="John Doe",
        phone="+94771234567",
        appointments=[
            SeedAppointment("Cardiology", offset_days=7, status=AppointmentStatus.SCHEDULED),
            SeedAppointment(
                "General Medicine", offset_days=-21, status=AppointmentStatus.COMPLETED
            ),
        ],
    ),
    SeedPatient(full_name="Donva J.", phone="+94772345678"),
    SeedPatient(
        full_name="Nimal Perera",
        phone="+94711234567",
        appointments=[
            SeedAppointment("Dermatology", offset_days=3, status=AppointmentStatus.SCHEDULED),
            SeedAppointment(
                "General Medicine", offset_days=-40, status=AppointmentStatus.COMPLETED
            ),
        ],
    ),
    SeedPatient(
        full_name="Kamala Silva",
        phone="+94761234567",
        appointments=[
            SeedAppointment("Orthopedics", offset_days=-10, status=AppointmentStatus.NO_SHOW),
        ],
    ),
    SeedPatient(full_name="Sunil Fernando", phone="+94701234567"),
]


async def seed_database(session: AsyncSession, *, now: datetime.datetime) -> tuple[int, int]:
    """Seed patients and appointments idempotently.

    Returns a ``(patients, appointments)`` count of rows present after seeding.
    """
    patients = PatientRepository(session)
    appointments = AppointmentRepository(session)

    patient_count = 0
    appointment_count = 0
    for spec in SEED_PATIENTS:
        phone = normalize_phone(spec.phone)
        patient, _created = await patients.upsert_by_phone(phone, spec.full_name)
        patient_count += 1

        # Replace this patient's appointments so re-runs never duplicate.
        await session.execute(delete(Appointment).where(Appointment.patient_id == patient.id))
        for appt in spec.appointments:
            await appointments.add(
                patient.id,
                appt.department,
                now + datetime.timedelta(days=appt.offset_days),
                status=appt.status,
                notes=appt.notes,
            )
            appointment_count += 1

    return patient_count, appointment_count


async def main() -> None:
    """Configure logging, open the database, and run the seed in one transaction."""
    settings = get_settings()
    configure_logging(settings)
    database = Database.from_settings(settings)
    try:
        async with database.sessionmaker() as session:
            now = datetime.datetime.now(datetime.UTC)
            patients, appointments = await seed_database(session, now=now)
            await session.commit()
        _logger.info("seed.completed", patients=patients, appointments=appointments)
    finally:
        await database.dispose()


if __name__ == "__main__":
    asyncio.run(main())
