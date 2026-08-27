"""SQLAlchemy ORM models.

Importing this package imports every model module so that ``Base.metadata`` is
fully populated — this is what Alembic's environment and the test harness rely on
to see the complete schema.
"""

from __future__ import annotations

from sahana_api.models.appointment import Appointment
from sahana_api.models.base import Base
from sahana_api.models.enums import AppointmentStatus, MessageRole, PatientStatus
from sahana_api.models.message import Message
from sahana_api.models.patient import Patient
from sahana_api.models.session import DEFAULT_SESSION_TITLE, Session

__all__ = [
    "DEFAULT_SESSION_TITLE",
    "Appointment",
    "AppointmentStatus",
    "Base",
    "Message",
    "MessageRole",
    "Patient",
    "PatientStatus",
    "Session",
]
