"""Non-streaming synthesizer: ``complete`` today, ``stream`` in Phase 6.

Route-appropriate system prompts live in :mod:`sahana_api.tools.prompts`. Citations
and the CRM table are taken from the tool result — the model never invents
sources, and CRM figures that the model drops or alters are replaced by the
authoritative payload.
"""

from __future__ import annotations

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import StructuredTable
from sahana_api.graph.tools import SynthesisResult, ToolResult
from sahana_api.llm.base import ChatModel, Message
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


class CompletingSynthesizer:
    """Synthesizer that calls ``ChatModel.complete``. Phase 6 swaps this for streaming."""

    def __init__(self, model: ChatModel | None) -> None:
        self._model = model

    async def synthesize(self, question: str, result: ToolResult) -> SynthesisResult:
        status = str(result.metadata.get("status", ""))
        if status in _PASSTHROUGH_STATUSES or self._model is None:
            answer = result.payload if result.payload else NOT_FOUND_MESSAGE
            return SynthesisResult(
                answer=answer,
                citations=list(result.citations),
                structured=result.structured,
            )

        system = prompt_for(result.route, status)
        user = _user_message(question, result)
        completion = await self._model.complete([Message("system", system), Message("user", user)])
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
        )


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
