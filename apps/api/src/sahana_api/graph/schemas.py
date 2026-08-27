"""Structured schemas for the classifier nodes and the decision verdict.

``GuardrailVerdict`` and ``RouteDecision`` are the JSON-schema-constrained outputs
of the guardrail and router classifiers (validated by ``complete_structured``).
``Route`` enumerates the four tool paths; refusal is the guardrail's job, not a
route. ``Verdict`` is the single decision the pure fan-in emits.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Route(StrEnum):
    """A tool path the router may choose. Refusal is not a route."""

    CRM = "crm"
    RAG = "rag"
    DIRECT = "direct"
    WEB_SEARCH = "web_search"


class Verdict(StrEnum):
    """The single decision emitted by ``decide_node``."""

    OUT_OF_SCOPE = "out_of_scope"
    CACHE_HIT = "cache_hit"
    PROCEED = "proceed"


class GuardrailVerdict(BaseModel):
    """Whether a question is within hospital-assistant scope.

    A future safety dimension (e.g. emergency escalation) would extend this model
    and the guardrail node; Phase 4 needs only in-scope classification.
    """

    in_scope: bool = Field(description="True if the question is about hospital services.")
    category: str = Field(
        description="Short category label, e.g. 'clinical', 'logistics', 'off_topic'."
    )
    reason: str = Field(description="Brief justification, free of personal data.")


class RouteDecision(BaseModel):
    """The router's choice among the four tool paths."""

    route: Route = Field(description="The tool path best suited to answer the question.")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in the chosen route.")
    reason: str = Field(description="Brief justification, free of personal data.")
    needs_patient_identity: bool = Field(
        description="True when answering requires resolving the caller's patient identity."
    )
