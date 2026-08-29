"""Node factories for the decision graph.

Each factory binds a node to its dependencies (models, cache, tools, synth,
settings) and returns an async node function of the graph state. The three
classifier nodes write distinct keys; every node contributes one PII-free trace
entry via the additive ``trace`` reducer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.graph.context import RequestContext, TraceEntry
from sahana_api.graph.decide import decide
from sahana_api.graph.prompts import GUARDRAIL_SYSTEM, ROUTER_SYSTEM
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision
from sahana_api.graph.state import GraphState
from sahana_api.graph.tools import ToolRegistry, ToolRequest
from sahana_api.llm.base import Message
from sahana_api.llm.registry import ModelRegistry
from sahana_api.memory.recall import SessionProvider, recall
from sahana_api.phone import InvalidPhoneNumberError, normalize_phone
from sahana_api.repositories.patients import PatientRepository

Node = Callable[[GraphState], Awaitable[GraphState]]


def make_guardrail_node(models: ModelRegistry) -> Node:
    """Classify whether the question is in scope."""

    async def guardrail_node(state: GraphState) -> GraphState:
        model = models.get_model("guardrail")
        completion = await model.complete_structured(
            [Message("system", GUARDRAIL_SYSTEM), Message("user", state["question"])],
            GuardrailVerdict,
        )
        verdict = completion.value
        entry = TraceEntry(
            "guardrail", {"in_scope": verdict.in_scope, "category": verdict.category}
        )
        return {"guardrail": verdict, "trace": [entry]}

    return guardrail_node


def make_router_node(models: ModelRegistry) -> Node:
    """Choose a tool path among crm | rag | direct | web_search."""

    async def router_node(state: GraphState) -> GraphState:
        model = models.get_model("router")
        completion = await model.complete_structured(
            [Message("system", ROUTER_SYSTEM), Message("user", state["question"])],
            RouteDecision,
        )
        decision = completion.value
        entry = TraceEntry(
            "router",
            {
                "route": decision.route.value,
                "confidence": round(decision.confidence, 4),
                "needs_patient_identity": decision.needs_patient_identity,
            },
        )
        return {"route": decision, "trace": [entry]}

    return router_node


def make_cag_node(cag: CagCache | None) -> Node:
    """Peek the nearest cached candidate (route-agnostic, ungated)."""

    async def cag_node(state: GraphState) -> GraphState:
        if cag is None:
            return {"cag": None, "trace": [TraceEntry("cag", {"available": False})]}
        candidate = await cag.peek(state["question"])
        data: dict[str, Any] = {"available": True, "hit": candidate is not None}
        if candidate is not None:
            data |= {
                "score": round(candidate.score, 4),
                "route": candidate.route,
                "expired": candidate.expired,
            }
        return {"cag": candidate, "trace": [TraceEntry("cag", data)]}

    return cag_node


def make_decide_node(settings: Settings) -> Node:
    """Fan the three results into one verdict with pure logic (no LLM, no I/O)."""

    fallback = Route(settings.router_fallback_route)

    async def decide_node(state: GraphState) -> GraphState:
        outcome = decide(
            state.get("guardrail"),
            state.get("route"),
            state.get("cag"),
            threshold=settings.cag_similarity_threshold,
            cacheable_routes=settings.cag_cacheable_routes,
            min_confidence=settings.router_min_confidence,
            fallback_route=fallback,
            route_match_policy=settings.cag_route_match_policy,
        )
        entry = TraceEntry(
            "decide",
            {
                "verdict": outcome.verdict.value,
                "branch": outcome.branch,
                "route": outcome.route.value if outcome.route is not None else None,
                "cache_gated_in": outcome.cache_gated_in,
                "detail": outcome.detail,
            },
        )
        return {"verdict": outcome.verdict, "route_taken": outcome.route, "trace": [entry]}

    return decide_node


def make_refusal_node(refusal_message: str) -> Node:
    """Serve the templated refusal. No LLM, no tools."""

    async def refusal_node(state: GraphState) -> GraphState:
        return {"answer": refusal_message, "trace": [TraceEntry("refusal", {"served": True})]}

    return refusal_node


def make_cached_answer_node() -> Node:
    """Serve the cached candidate's answer."""

    async def cached_answer_node(state: GraphState) -> GraphState:
        candidate = state.get("cag")
        answer = candidate.answer if candidate is not None else ""
        route = candidate.route if candidate is not None else None
        return {
            "answer": answer,
            "trace": [TraceEntry("cached_answer", {"served": True, "route": route})],
        }

    return cached_answer_node


def make_tool_then_synth_node(tools: ToolRegistry, fallback_route: Route) -> Node:
    """Run the chosen route's tool with the resolved context; store the result.

    Synthesis (complete or stream) happens in the pipeline layer so the same tool
    result can be answered synchronously or streamed. The node's name is kept for
    the reasoning trace.
    """

    async def tool_then_synth_node(state: GraphState) -> GraphState:
        route = state.get("route_taken") or fallback_route
        base = state["context"]
        resolved_patient_id = state.get("resolved_patient_id") or base.patient_id
        context = RequestContext(
            session_id=base.session_id, patient_id=resolved_patient_id, phone=base.phone
        )
        result = await tools.get(route).run(ToolRequest(state["question"], context))
        entry = TraceEntry(
            "tool_then_synth",
            {
                "route": route.value,
                "status": str(result.metadata.get("status", "ok")),
                "citations": len(result.citations),
                "structured": result.structured is not None,
            },
        )
        return {"tool_result": result, "route_taken": route, "trace": [entry]}

    return tool_then_synth_node


def make_patient_lookup_node(session_provider: SessionProvider) -> Node:
    """Resolve the caller's phone to a patient id (own-identity only)."""

    async def patient_lookup_node(state: GraphState) -> GraphState:
        context = state["context"]
        resolved = context.patient_id
        if resolved is None and context.phone:
            try:
                phone = normalize_phone(context.phone)
            except InvalidPhoneNumberError:
                phone = None
            if phone is not None:
                async with session_provider() as session:
                    patient = await PatientRepository(session).get_by_phone(phone)
                    resolved = patient.id if patient is not None else None
        entry = TraceEntry("patient_lookup", {"identified": resolved is not None})
        return {"resolved_patient_id": resolved, "trace": [entry]}

    return patient_lookup_node


def make_memory_recall_node(session_provider: SessionProvider, recall_turns: int) -> Node:
    """Recall the rolling summary plus the last N turns for the session."""

    async def memory_recall_node(state: GraphState) -> GraphState:
        session_id = state["context"].session_id
        if session_id is None:
            return {"memory": None, "trace": [TraceEntry("memory_recall", {"available": False})]}
        memory = await recall(session_provider, session_id, recall_turns=recall_turns)
        entry = TraceEntry(
            "memory_recall",
            {"turns": len(memory.turns), "has_summary": memory.summary is not None},
        )
        return {"memory": memory, "trace": [entry]}

    return memory_recall_node
