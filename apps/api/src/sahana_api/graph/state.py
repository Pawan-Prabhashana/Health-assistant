"""Graph state schema and trace types.

The three classifier nodes write to distinct keys (``guardrail``, ``route``,
``cag``) so their concurrent writes never conflict. The single shared key,
``trace``, uses an explicit additive reducer so each node's contribution is
merged rather than overwritten. The trace is observability and must never carry
PII or raw patient data.
"""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from sahana_api.cag.cache import CagCandidate
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision, Verdict

__all__ = [
    "CagCandidate",
    "GraphState",
    "RequestContext",
    "TraceEntry",
]


@dataclass(frozen=True)
class RequestContext:
    """Caller context, passed in (not resolved here).

    Patient identity, when known, is resolved upstream (Phase 6) and passed in;
    the graph never resolves identity itself.
    """

    session_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None


@dataclass(frozen=True)
class TraceEntry:
    """One node's structured contribution to the reasoning trace (PII-free)."""

    node: str
    data: dict[str, Any] = field(default_factory=dict)


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
    verdict: Verdict | None
    route_taken: Route | None
    answer: str | None
    trace: Annotated[list[TraceEntry], operator.add]
