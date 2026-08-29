"""Synthesizer: ``complete`` (sync) and ``stream`` (SSE) over the synth model.

Route-appropriate system prompts live in :mod:`sahana_api.tools.prompts`. Citations
and the CRM table come from the tool result — the model never invents sources, and
CRM figures the model drops or alters are replaced by the authoritative payload.
Recalled short-term memory (``history``) is prepended to ground the reply in the
conversation. The stream yields text deltas then a :class:`SynthStreamEnd` carrying
the final result (answer, citations, structured payload, and captured usage).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from sahana_api.graph.context import StructuredTable
from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import SynthesisResult, SynthStreamEnd, ToolResult
from sahana_api.llm.base import ChatModel, Message, TextDelta
from sahana_api.logging import get_logger
from sahana_api.tools.prompts import (
    CONCIERGE_SYSTEM,
    CRM_FRAMING_SYSTEM,
    GROUNDED_SYSTEM,
    NOT_FOUND_MESSAGE,
)

_logger = get_logger("sahana_api.tools.synth")

_PASSTHROUGH_STATUSES = frozenset({"identify_required", "not_found", "unavailable"})


def prompt_for(route: Route, status: str) -> str:
    """Return the system prompt the synthesizer uses for ``route`` (and status)."""
    if status in _PASSTHROUGH_STATUSES:
        return ""
    if route is Route.DIRECT:
        return CONCIERGE_SYSTEM
    if route is Route.CRM:
        return CRM_FRAMING_SYSTEM
    return GROUNDED_SYSTEM


def _figures_intact(table: StructuredTable, answer: str) -> bool:
    """Return whether every cell of the authoritative table appears in ``answer``."""
    return all(cell in answer for row in table.rows for cell in row)


def _user_message(question: str, result: ToolResult) -> str:
    if result.route is Route.DIRECT:
        return question
    if result.route is Route.CRM:
        return (
            f"The user's message:\n{question}\n\n"
            f"Authoritative patient record (copy every figure verbatim):\n{result.payload}"
        )
    return (
        f"Question:\n{question}\n\nContext (cite only the sources labelled here):\n{result.payload}"
    )


def _is_passthrough(result: ToolResult) -> bool:
    return str(result.metadata.get("status", "")) in _PASSTHROUGH_STATUSES


class CompletingSynthesizer:
    """Synthesizer over ``ChatModel``: ``synthesize`` (complete) and ``stream``."""

    def __init__(self, model: ChatModel | None) -> None:
        self._model = model

    def _messages(
        self, question: str, result: ToolResult, history: Sequence[Message] | None
    ) -> list[Message]:
        system = prompt_for(result.route, str(result.metadata.get("status", "")))
        return [
            Message("system", system),
            *(history or []),
            Message("user", _user_message(question, result)),
        ]

    async def synthesize(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> SynthesisResult:
        if _is_passthrough(result) or self._model is None:
            answer = result.payload if result.payload else NOT_FOUND_MESSAGE
            return SynthesisResult(
                answer=answer, citations=list(result.citations), structured=result.structured
            )

        completion = await self._model.complete(self._messages(question, result, history))
        answer = completion.text.strip()
        if (
            result.route is Route.CRM
            and result.structured is not None
            and not _figures_intact(result.structured, answer)
        ):
            _logger.warning("synth.crm_figures_reverted")
            answer = result.payload

        return SynthesisResult(
            answer=answer,
            citations=list(result.citations),
            structured=result.structured,
            usage=completion.usage,
        )

    async def stream(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> AsyncIterator[str | SynthStreamEnd]:
        """Yield text deltas then a :class:`SynthStreamEnd`.

        Pass-through statuses and the CRM path do not stream token-by-token: they
        emit a single terminal event with the deterministic/verified answer.
        """
        if _is_passthrough(result) or result.route is Route.CRM or self._model is None:
            yield SynthStreamEnd(await self.synthesize(question, result, history=history))
            return

        pieces: list[str] = []
        usage = None
        async for event in self._model.stream_events(self._messages(question, result, history)):
            if isinstance(event, TextDelta):
                pieces.append(event.text)
                yield event.text
            else:
                usage = event.usage

        yield SynthStreamEnd(
            SynthesisResult(
                answer="".join(pieces).strip(),
                citations=list(result.citations),
                structured=result.structured,
                usage=usage,
            )
        )
