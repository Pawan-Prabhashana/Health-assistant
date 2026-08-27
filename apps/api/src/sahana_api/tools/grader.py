"""CRAG relevance grading.

A cheap LLM grades the retrieved chunks for actual relevance to the question in a
single batched structured call (not one call per chunk). Relevance — not a raw
similarity score — decides usefulness; see ADR 0011.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field

from sahana_api.kb.retriever import ScoredChunk
from sahana_api.llm.base import ChatModel, Message
from sahana_api.tools.prompts import GRADER_SYSTEM


class ChunkGrade(BaseModel):
    """A single passage's relevance grade."""

    index: int = Field(description="The passage index shown in the prompt.")
    relevant: bool = Field(description="Whether the passage could help answer the question.")


class RelevanceGrades(BaseModel):
    """The grader's batched output, one entry per graded passage."""

    grades: list[ChunkGrade]


class RelevanceGrader:
    """Grades retrieved chunks for relevance using a cheap model."""

    def __init__(self, model: ChatModel | None) -> None:
        self._model = model

    async def grade(self, question: str, chunks: Sequence[ScoredChunk]) -> list[bool]:
        """Return a per-chunk relevance flag, aligned to ``chunks`` order."""
        if not chunks:
            return []
        if self._model is None:
            return [False] * len(chunks)

        listing = "\n\n".join(f"[{index}] {chunk.text}" for index, chunk in enumerate(chunks))
        user = f"Question: {question}\n\nPassages:\n{listing}\n\nGrade each passage by its index."
        completion = await self._model.complete_structured(
            [Message("system", GRADER_SYSTEM), Message("user", user)],
            RelevanceGrades,
        )

        relevant = [False] * len(chunks)
        for grade in completion.value.grades:
            if 0 <= grade.index < len(chunks):
                relevant[grade.index] = grade.relevant
        return relevant
