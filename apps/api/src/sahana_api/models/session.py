"""Conversation session (thread) aggregate."""

from __future__ import annotations

import datetime
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahana_api.models.base import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from sahana_api.models.message import Message
    from sahana_api.models.patient import Patient

DEFAULT_SESSION_TITLE = "New conversation"


class Session(TimestampMixin, Base):
    """A conversation thread, optionally associated with a patient.

    ``patient_id`` is nullable because a session may begin before the caller
    identifies themselves; the chat layer associates it once the phone resolves.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_patient_id", "patient_id"),
        Index("ix_sessions_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="CASCADE"),
        nullable=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, default=DEFAULT_SESSION_TITLE)
    # Rolling short-term memory summary; refreshed by /chat/summarize (Phase 6).
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_updated_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    patient: Mapped[Patient | None] = relationship(back_populates="sessions")
    messages: Mapped[list[Message]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )
