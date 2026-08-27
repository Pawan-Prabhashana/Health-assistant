"""Patient aggregate root."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahana_api.models.base import Base, TimestampMixin, pg_enum, uuid_pk
from sahana_api.models.enums import PatientStatus

if TYPE_CHECKING:
    from sahana_api.models.appointment import Appointment
    from sahana_api.models.session import Session


class Patient(TimestampMixin, Base):
    """A patient identified by a normalized E.164 phone number.

    ``mrn`` is a human-readable medical record number allocated from the
    ``patient_mrn_seq`` sequence at insert time, yielding values such as
    ``P-10023``. ``phone`` is the identity key the chat layer resolves callers by.
    """

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = uuid_pk()
    mrn: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
        server_default=text("'P-' || nextval('patient_mrn_seq')"),
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PatientStatus] = mapped_column(
        pg_enum(PatientStatus, "patient_status"),
        nullable=False,
        server_default=text(f"'{PatientStatus.STABLE.value}'"),
    )

    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessions: Mapped[list[Session]] = relationship(
        back_populates="patient",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
