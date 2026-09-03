"""Session repository."""

from __future__ import annotations

import datetime
import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sahana_api.models.message import Message
from sahana_api.models.session import DEFAULT_SESSION_TITLE, Session


class SessionRepository:
    """Data access for the conversation-session aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, patient_id: uuid.UUID | None, title: str | None) -> Session:
        """Create a new session thread and return it."""
        thread = Session(patient_id=patient_id, title=title or DEFAULT_SESSION_TITLE)
        self._session.add(thread)
        await self._session.flush()
        return thread

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Return the session with ``session_id`` or ``None``."""
        return await self._session.get(Session, session_id)

    async def get_with_messages(self, session_id: uuid.UUID) -> Session | None:
        """Return the session with its messages eagerly loaded, or ``None``."""
        result = await self._session.execute(
            select(Session).where(Session.id == session_id).options(selectinload(Session.messages))
        )
        return result.scalar_one_or_none()

    async def list_for_patient(
        self, patient_id: uuid.UUID, *, limit: int, offset: int
    ) -> Sequence[Session]:
        """Return a patient's sessions, newest first, bounded by limit/offset."""
        result = await self._session.execute(
            select(Session)
            .where(Session.patient_id == patient_id)
            .order_by(Session.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_for_patient(self, patient_id: uuid.UUID) -> int:
        """Return how many sessions a patient owns (for the per-identity cap)."""
        result = await self._session.execute(
            select(func.count()).select_from(Session).where(Session.patient_id == patient_id)
        )
        return int(result.scalar_one())

    async def delete_by_id(self, session_id: uuid.UUID) -> bool:
        """Delete a session and cascade its messages. Returns whether one matched."""
        thread = await self.get_by_id(session_id)
        if thread is None:
            return False
        await self._session.delete(thread)
        await self._session.flush()
        return True

    async def set_summary(self, session_id: uuid.UUID, summary: str) -> None:
        """Store the rolling short-term-memory summary for a session."""
        thread = await self.get_by_id(session_id)
        if thread is None:
            return
        thread.summary = summary
        thread.summary_updated_at = datetime.datetime.now(datetime.UTC)
        await self._session.flush()

    async def clear_memory(self, session_id: uuid.UUID) -> bool:
        """Delete a session's messages and summary, keeping the session record.

        Returns whether the session exists.
        """
        thread = await self.get_by_id(session_id)
        if thread is None:
            return False
        await self._session.execute(delete(Message).where(Message.session_id == session_id))
        thread.summary = None
        thread.summary_updated_at = None
        await self._session.flush()
        return True
