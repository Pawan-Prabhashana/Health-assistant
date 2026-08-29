"""Rolling short-term-memory summarization.

Compresses the older turns of a session into a bounded running summary using a
cheap model role, so long threads stay within a bounded context. Recall reads the
summary; ``/chat/summarize`` refreshes it. Summaries carry no phone numbers or
identifiers (see ADR 0012).
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.llm.base import ChatModel, Message
from sahana_api.repositories.messages import MessageRepository
from sahana_api.repositories.sessions import SessionRepository

SUMMARY_SYSTEM = (
    "You maintain a running summary of a hospital-assistant conversation. Rewrite "
    "the summary so it preserves the key facts and the user's intent in under 120 "
    "words. Do not include phone numbers, medical record numbers, or other "
    "identifiers."
)


async def summarize_session(
    session: AsyncSession,
    model: ChatModel,
    session_id: uuid.UUID,
    *,
    keep_recent: int,
) -> str | None:
    """Refresh the session's rolling summary from its older turns.

    Returns the new summary, or ``None`` when there is nothing to summarize.
    """
    messages = await MessageRepository(session).list_for_session(session_id)
    older = messages[:-keep_recent] if keep_recent > 0 else list(messages)
    if not older:
        return None

    transcript = "\n".join(f"{message.role.value}: {message.content}" for message in older)
    completion = await model.complete(
        [Message("system", SUMMARY_SYSTEM), Message("user", transcript)]
    )
    summary = completion.text.strip()
    await SessionRepository(session).set_summary(session_id, summary)
    return summary
