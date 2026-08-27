"""Message repository (used by the chat pipeline in a later phase)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
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

    async def list_for_session(self, session_id: uuid.UUID) -> Sequence[Message]:
        """Return a session's messages in chronological order."""
        result = await self._session.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        return result.scalars().all()
