"""Conversation message (written by the chat pipeline in a later phase)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sahana_api.models.base import Base, CreatedAtMixin, pg_enum, uuid_pk
from sahana_api.models.enums import MessageRole

if TYPE_CHECKING:
    from sahana_api.models.session import Session


class Message(CreatedAtMixin, Base):
    """A single message in a session.

    ``meta`` maps to the ``metadata`` JSONB column (the attribute name avoids the
    reserved ``Base.metadata``). It is reserved for route taken, latency, and
    token accounting recorded by later phases.
    """

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_session_id_created_at", "session_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[MessageRole] = mapped_column(pg_enum(MessageRole, "message_role"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    session: Mapped[Session] = relationship(back_populates="messages")
