"""Message repository (used by the chat pipeline in a later phase)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.models.enums import MessageRole
from sahana_api.models.message import Message


class MessageRepository:
    """Data access for conversation messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        session_id: uuid.UUID,
        role: MessageRole,
        content: str,
        meta: dict[str, Any] | None = None,
    ) -> Message:
        """Append a message to a session and return it."""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            meta=meta if meta is not None else {},
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def list_for_session(
        self, session_id: uuid.UUID, *, limit: int | None = None, offset: int = 0
    ) -> Sequence[Message]:
        """Return a session's messages in chronological order, optionally paginated."""
        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        result = await self._session.execute(query)
        return result.scalars().all()

    async def recent(self, session_id: uuid.UUID, limit: int) -> list[Message]:
        """Return the most recent ``limit`` messages in chronological order."""
        if limit <= 0:
            return []
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        return list(reversed(result.scalars().all()))

    async def count_for_session(self, session_id: uuid.UUID) -> int:
        """Return the number of messages in a session."""
        result = await self._session.execute(
            select(func.count()).select_from(Message).where(Message.session_id == session_id)
        )
        return int(result.scalar_one())
