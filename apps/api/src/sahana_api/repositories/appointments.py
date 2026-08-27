"""Appointment repository (read by the CRM tool in a later phase)."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.models.appointment import Appointment
from sahana_api.models.enums import AppointmentStatus


class AppointmentRepository:
    """Data access for appointments."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        patient_id: uuid.UUID,
        department: str,
        scheduled_for: datetime.datetime,
        *,
        status: AppointmentStatus = AppointmentStatus.SCHEDULED,
        notes: str | None = None,
    ) -> Appointment:
        """Create an appointment and return it."""
        appointment = Appointment(
            patient_id=patient_id,
            department=department,
            scheduled_for=scheduled_for,
            status=status,
            notes=notes,
        )
        self._session.add(appointment)
        await self._session.flush()
        return appointment

    async def list_for_patient(self, patient_id: uuid.UUID) -> Sequence[Appointment]:
        """Return a patient's appointments, earliest scheduled first."""
        result = await self._session.execute(
            select(Appointment)
            .where(Appointment.patient_id == patient_id)
            .order_by(Appointment.scheduled_for.asc())
        )
        return result.scalars().all()

    async def next_upcoming_for_patient(
        self, patient_id: uuid.UUID, *, now: datetime.datetime
    ) -> Appointment | None:
        """Return the patient's soonest scheduled future appointment, if any."""
        result = await self._session.execute(
            select(Appointment)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.SCHEDULED,
                Appointment.scheduled_for >= now,
            )
            .order_by(Appointment.scheduled_for.asc())
            .limit(1)
        )
        return result.scalar_one_or_none()
