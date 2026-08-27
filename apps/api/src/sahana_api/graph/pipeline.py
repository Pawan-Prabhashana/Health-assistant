"""Graph assembly and the ``run_pipeline`` service function.

``build_graph`` compiles the LangGraph once from a set of dependencies; the
compiled graph is reused for every request (never rebuilt per call).
``run_pipeline`` invokes it and returns a typed :class:`PipelineResult`. Phase 6
wires this into the chat endpoints with streaming; Phase 5 swaps the stub tool
handlers and synth for the real ones without touching the graph.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.graph.nodes import (
    Node,
    make_cached_answer_node,
    make_cag_node,
    make_decide_node,
    make_guardrail_node,
    make_refusal_node,
    make_router_node,
    make_tool_then_synth_node,
)
from sahana_api.graph.schemas import Route, Verdict
from sahana_api.graph.state import GraphState, RequestContext, TraceEntry
from sahana_api.graph.tools import (
    StubSynthesizer,
    Synthesizer,
    ToolRegistry,
    build_stub_registry,
)
from sahana_api.llm.registry import ModelRegistry

CompiledGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]


class PipelineError(RuntimeError):
    """Raised when the graph returns an invalid result (a wiring invariant broke)."""


@dataclass(frozen=True)
class PipelineDeps:
    """Everything the graph needs, injected so tests and phases can swap parts."""

    models: ModelRegistry
    tools: ToolRegistry
    synth: Synthesizer
    cag: CagCache | None
    settings: Settings


@dataclass(frozen=True)
class PipelineResult:
    """The outcome of one pipeline run."""

    verdict: Verdict
    route: Route | None
    answer: str
    trace: list[TraceEntry]


def build_stub_deps(
    settings: Settings, models: ModelRegistry, cag: CagCache | None
) -> PipelineDeps:
    """Assemble deps with the Phase 4 stub tool registry and stub synthesizer."""
    return PipelineDeps(
        models=models,
        tools=build_stub_registry(),
        synth=StubSynthesizer(),
        cag=cag,
        settings=settings,
    )


def _route_from_verdict(state: GraphState) -> str:
    """Conditional-edge dispatch from the decided verdict to a terminal."""
    verdict = state.get("verdict")
    if verdict == Verdict.OUT_OF_SCOPE:
        return "refusal"
    if verdict == Verdict.CACHE_HIT:
        return "cached_answer"
    return "tool_then_synth"


def _add_node(
    builder: StateGraph[GraphState, Any, GraphState, GraphState], name: str, node: Node
) -> None:
    # langgraph's StateNode protocol bound (StateLike) is not inferred for a
    # TypedDict state under mypy strict, though the node is valid at runtime and
    # accepted by pyright. Isolate the single unavoidable ignore here.
    builder.add_node(name, node)  # type: ignore[call-overload]


def build_graph(deps: PipelineDeps) -> CompiledGraph:
    """Compile the parallel-classifier decision graph once."""
    builder: StateGraph[GraphState, Any, GraphState, GraphState] = StateGraph(GraphState)

    _add_node(builder, "guardrail", make_guardrail_node(deps.models))
    _add_node(builder, "router", make_router_node(deps.models))
    _add_node(builder, "cag", make_cag_node(deps.cag))
    _add_node(builder, "decide", make_decide_node(deps.settings))
    _add_node(builder, "refusal", make_refusal_node(deps.settings.refusal_message))
    _add_node(builder, "cached_answer", make_cached_answer_node())
    _add_node(
        builder,
        "tool_then_synth",
        make_tool_then_synth_node(
            deps.tools, deps.synth, Route(deps.settings.router_fallback_route)
        ),
    )

    # Fan out to the three classifiers, then fan them all into decide.
    for classifier in ("guardrail", "router", "cag"):
        builder.add_edge(START, classifier)
        builder.add_edge(classifier, "decide")

    builder.add_conditional_edges(
        "decide",
        _route_from_verdict,
        {
            "refusal": "refusal",
            "cached_answer": "cached_answer",
            "tool_then_synth": "tool_then_synth",
        },
    )

    for terminal in ("refusal", "cached_answer", "tool_then_synth"):
        builder.add_edge(terminal, END)

    return builder.compile()


async def run_pipeline(
    graph: CompiledGraph, question: str, context: RequestContext
) -> PipelineResult:
    """Run the compiled graph for one question and return a typed result."""
    initial: GraphState = {"question": question, "context": context, "trace": []}
    final = await graph.ainvoke(initial)

    verdict = final.get("verdict")
    if verdict is None:
        raise PipelineError("decision graph produced no verdict")

    return PipelineResult(
        verdict=verdict,
        route=final.get("route_taken"),
        answer=final.get("answer") or "",
        trace=final.get("trace", []),
    )
