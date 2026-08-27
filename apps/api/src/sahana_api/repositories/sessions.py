"""Session repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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

    async def delete_by_id(self, session_id: uuid.UUID) -> bool:
        """Delete a session and cascade its messages. Returns whether one matched."""
        thread = await self.get_by_id(session_id)
        if thread is None:
            return False
        await self._session.delete(thread)
        await self._session.flush()
        return True
