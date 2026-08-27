"""Typed async repositories, one per aggregate.

Repositories own all query construction and return ORM models. SQLAlchemy types
never leak past this boundary: routers and services depend on repositories, not
on ``select``/``Session`` internals.
"""

from __future__ import annotations

from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.patients import DEFAULT_PATIENT_NAME, PatientRepository
from sahana_api.repositories.sessions import SessionRepository

__all__ = [
    "DEFAULT_PATIENT_NAME",
    "AppointmentRepository",
    "MessageRepository",
    "PatientRepository",
    "SessionRepository",
]
