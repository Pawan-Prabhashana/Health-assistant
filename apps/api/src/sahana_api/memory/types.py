"""Short-term memory types.

Recall assembles a bounded synth context as a rolling summary plus the last N raw
turns, so context stays bounded regardless of thread length (see ADR 0012).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sahana_api.llm.base import Message, MessageRole


@dataclass(frozen=True)
class MemoryTurn:
    """One recalled conversation turn."""

    role: MessageRole
    content: str


@dataclass(frozen=True)
class MemoryContext:
    """A bounded conversational context: a rolling summary plus recent turns."""

    summary: str | None = None
    turns: list[MemoryTurn] = field(default_factory=list)

    def is_empty(self) -> bool:
        return self.summary is None and not self.turns


def memory_to_messages(memory: MemoryContext | None) -> list[Message]:
    """Convert recalled memory into LLM messages to prepend to a synth call."""
    if memory is None or memory.is_empty():
        return []
    messages: list[Message] = []
    if memory.summary:
        messages.append(Message("system", f"Summary of the conversation so far: {memory.summary}"))
    messages.extend(Message(turn.role, turn.content) for turn in memory.turns)
    return messages
