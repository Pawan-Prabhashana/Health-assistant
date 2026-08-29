"""Graph state schema and trace types.

The five fan-out nodes write distinct keys (``guardrail``, ``route``, ``cag``,
``resolved_patient_id``, ``memory``) so their concurrent writes never conflict.
The single shared key, ``trace``, uses an explicit additive reducer so each
node's contribution is merged rather than overwritten. The trace is observability
and must never carry PII or raw patient data.
"""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, TypedDict

from sahana_api.cag.cache import CagCandidate
from sahana_api.graph.context import RequestContext, StructuredTable, TraceEntry
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision, Verdict
from sahana_api.graph.tools import ToolResult
from sahana_api.memory.types import MemoryContext

__all__ = [
    "CagCandidate",
    "GraphState",
    "MemoryContext",
    "RequestContext",
    "StructuredTable",
    "ToolResult",
    "TraceEntry",
]


class GraphState(TypedDict, total=False):
    """The decision graph's shared state.

    ``total=False`` because nodes populate their keys as they run; the initial
    input provides only ``question``, ``context``, and an empty ``trace``.
    """

    question: str
    context: RequestContext
    guardrail: GuardrailVerdict | None
    route: RouteDecision | None
    cag: CagCandidate | None
    resolved_patient_id: uuid.UUID | None
    memory: MemoryContext | None
    verdict: Verdict | None
    route_taken: Route | None
    tool_result: ToolResult | None
    answer: str | None
    citations: list[str]
    structured: StructuredTable | None
    trace: Annotated[list[TraceEntry], operator.add]
