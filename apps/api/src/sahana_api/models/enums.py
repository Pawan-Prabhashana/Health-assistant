"""Enumerations shared by the ORM and Pydantic layers.

Each enum is a :class:`enum.StrEnum` whose member *values* are the exact strings
persisted in Postgres. There is a single definition per concept, imported by both
the SQLAlchemy models and the Pydantic schemas, so the two layers can never drift.
"""

from __future__ import annotations

from enum import StrEnum


class PatientStatus(StrEnum):
    """Clinical status shown in the CRM reply."""

    STABLE = "stable"
    ADMITTED = "admitted"
    CRITICAL = "critical"
    DISCHARGED = "discharged"


class AppointmentStatus(StrEnum):
    """Lifecycle state of an appointment."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class MessageRole(StrEnum):
    """Author role of a conversation message."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
