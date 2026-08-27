"""Appointment records (CRM data read by a later phase; no REST endpoint yet)."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahana_api.models.base import Base, CreatedAtMixin, pg_enum, uuid_pk
from sahana_api.models.datetime import utc_timestamptz
from sahana_api.models.enums import AppointmentStatus

if TYPE_CHECKING:
    from sahana_api.models.patient import Patient


class Appointment(CreatedAtMixin, Base):
    """An appointment for a patient, in a department, at a point in time."""

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_patient_id_scheduled_for", "patient_id", "scheduled_for"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=False,
    )
    department: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(
        pg_enum(AppointmentStatus, "appointment_status"),
        nullable=False,
        server_default=text(f"'{AppointmentStatus.SCHEDULED.value}'"),
    )
    scheduled_for: Mapped[datetime.datetime] = utc_timestamptz(nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    patient: Mapped[Patient] = relationship(back_populates="appointments")
