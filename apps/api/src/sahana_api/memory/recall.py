"""Short-term memory recall for the graph's ``memory_recall_node``."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.llm.base import MessageRole
from sahana_api.memory.types import MemoryContext, MemoryTurn
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.sessions import SessionRepository

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# DB message role values are exactly the LLM message-role literals.
_ROLE_MAP: dict[str, MessageRole] = {"user": "user", "assistant": "assistant", "system": "system"}


async def recall(
    session_provider: SessionProvider, session_id: uuid.UUID, *, recall_turns: int
) -> MemoryContext:
    """Load the rolling summary and the last ``recall_turns`` raw turns for a session."""
    async with session_provider() as session:
        thread = await SessionRepository(session).get_by_id(session_id)
        summary = thread.summary if thread is not None else None
        messages = await MessageRepository(session).recent(session_id, recall_turns)
    turns = [
        MemoryTurn(role=_ROLE_MAP[message.role.value], content=message.content)
        for message in messages
    ]
    return MemoryContext(summary=summary, turns=turns)
