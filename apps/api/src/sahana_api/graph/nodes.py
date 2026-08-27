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
from sahana_api.graph.decide import decide
from sahana_api.graph.prompts import GUARDRAIL_SYSTEM, ROUTER_SYSTEM
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision
from sahana_api.graph.state import GraphState, TraceEntry
from sahana_api.graph.tools import Synthesizer, ToolRegistry, ToolRequest
from sahana_api.llm.base import Message
from sahana_api.llm.registry import ModelRegistry

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


def make_tool_then_synth_node(
    tools: ToolRegistry, synth: Synthesizer, fallback_route: Route
) -> Node:
    """Invoke the chosen route's tool handler, then synthesize the answer."""

    async def tool_then_synth_node(state: GraphState) -> GraphState:
        route = state.get("route_taken") or fallback_route
        handler = tools.get(route)
        result = await handler.run(ToolRequest(state["question"], state["context"]))
        answer = await synth.synthesize(state["question"], result)
        entry = TraceEntry(
            "tool_then_synth",
            {
                "route": route.value,
                "citations": len(result.citations),
                "stub": bool(result.metadata.get("stub", False)),
            },
        )
        return {"answer": answer, "trace": [entry]}

    return tool_then_synth_node
