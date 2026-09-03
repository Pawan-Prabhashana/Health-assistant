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


async def maybe_refresh_summary(
    session: AsyncSession,
    model: ChatModel,
    session_id: uuid.UUID,
    *,
    threshold: int,
    keep_recent: int,
) -> str | None:
    """Refresh the rolling summary when a thread has grown past ``threshold``.

    Recall returns the rolling summary plus the last ``keep_recent`` turns, so
    once a thread exceeds the threshold the summary must be refreshed as new turns
    arrive; otherwise turns older than the window but newer than the last summary
    fall out of context — a silent mid-conversation memory gap. Returns the new
    summary, or ``None`` when the thread is still within the threshold.
    """
    count = await MessageRepository(session).count_for_session(session_id)
    if count <= threshold:
        return None
    return await summarize_session(session, model, session_id, keep_recent=keep_recent)
