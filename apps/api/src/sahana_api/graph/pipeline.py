"""Graph assembly, the sync ``run_pipeline``, and the SSE ``stream_pipeline``.

``build_graph`` compiles the LangGraph once (never rebuilt per call) and returns a
:class:`CompiledPipeline` that also carries the synthesizer. The graph runs the
five-way fan-out, the pure-logic ``decide``, and the chosen tool, leaving the tool
result in state; synthesis (complete or stream) happens here so the same result is
answered synchronously or streamed. ``decide`` is unchanged: it reads only the
three classifiers. The two context nodes are added only when a ``session_provider``
is present, so graph-shape tests without one are unaffected.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.graph.context import RequestContext, StructuredTable, TraceEntry
from sahana_api.graph.nodes import (
    Node,
    make_cached_answer_node,
    make_cag_node,
    make_decide_node,
    make_guardrail_node,
    make_memory_recall_node,
    make_patient_lookup_node,
    make_refusal_node,
    make_router_node,
    make_tool_then_synth_node,
)
from sahana_api.graph.schemas import Route, Verdict
from sahana_api.graph.state import GraphState
from sahana_api.graph.tools import (
    StubSynthesizer,
    Synthesizer,
    SynthStreamEnd,
    ToolRegistry,
    build_stub_registry,
)
from sahana_api.llm.base import Message, Usage
from sahana_api.llm.registry import ModelRegistry
from sahana_api.memory.recall import SessionProvider
from sahana_api.memory.types import memory_to_messages

_CompiledGraph = CompiledStateGraph[GraphState, Any, GraphState, GraphState]


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
    session_provider: SessionProvider | None = None


@dataclass(frozen=True)
class PipelineResult:
    """The outcome of one pipeline run."""

    verdict: Verdict
    route: Route | None
    answer: str
    citations: list[str]
    structured: StructuredTable | None
    usage: Usage | None
    latency_ms: float
    trace: list[TraceEntry]


@dataclass(frozen=True)
class CompiledPipeline:
    """The compiled graph plus the synthesizer used to answer/stream terminals."""

    graph: _CompiledGraph
    synth: Synthesizer
    settings: Settings


# -- Streaming event protocol (serialized to SSE by the router) --------------
@dataclass(frozen=True)
class RoutingEvent:
    """Emitted once the verdict is known, so the UI can show the right state."""

    verdict: Verdict
    route: Route | None


@dataclass(frozen=True)
class DeltaEvent:
    """An incremental synth token."""

    text: str


@dataclass(frozen=True)
class FinalEvent:
    """The completed answer and its metadata."""

    result: PipelineResult


@dataclass(frozen=True)
class ErrorEvent:
    """A typed error event."""

    code: str
    message: str


type PipelineEvent = RoutingEvent | DeltaEvent | FinalEvent | ErrorEvent


def build_stub_deps(
    settings: Settings, models: ModelRegistry, cag: CagCache | None
) -> PipelineDeps:
    """Assemble deps with the stub tool registry and stub synthesizer (graph tests)."""
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


def build_graph(deps: PipelineDeps) -> CompiledPipeline:
    """Compile the parallel fan-out decision graph once."""
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
        make_tool_then_synth_node(deps.tools, Route(deps.settings.router_fallback_route)),
    )

    fan_out = ["guardrail", "router", "cag"]
    if deps.session_provider is not None:
        _add_node(builder, "patient_lookup", make_patient_lookup_node(deps.session_provider))
        _add_node(
            builder,
            "memory_recall",
            make_memory_recall_node(deps.session_provider, deps.settings.memory_recall_turns),
        )
        fan_out += ["patient_lookup", "memory_recall"]

    for node in fan_out:
        builder.add_edge(START, node)
        builder.add_edge(node, "decide")

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

    return CompiledPipeline(graph=builder.compile(), synth=deps.synth, settings=deps.settings)


async def _invoke(pipeline: CompiledPipeline, question: str, context: RequestContext) -> GraphState:
    initial: GraphState = {"question": question, "context": context, "trace": []}
    # ainvoke returns the final state; langgraph types it as a loose mapping.
    return cast(GraphState, await pipeline.graph.ainvoke(initial))


def _history(final: GraphState) -> Sequence[Message]:
    return memory_to_messages(final.get("memory"))


async def run_pipeline(
    pipeline: CompiledPipeline, question: str, context: RequestContext
) -> PipelineResult:
    """Run the compiled graph and synthesize (non-streaming) the answer."""
    started = perf_counter()
    final = await _invoke(pipeline, question, context)

    verdict = final.get("verdict")
    if verdict is None:
        raise PipelineError("decision graph produced no verdict")
    route = final.get("route_taken")
    trace = final.get("trace", [])

    if verdict is Verdict.PROCEED:
        tool_result = final.get("tool_result")
        if tool_result is None:
            raise PipelineError("proceed produced no tool result")
        synthesis = await pipeline.synth.synthesize(question, tool_result, history=_history(final))
        answer, citations = synthesis.answer, synthesis.citations
        structured, usage = synthesis.structured, synthesis.usage
    else:
        answer = final.get("answer") or ""
        citations = final.get("citations") or []
        structured = final.get("structured")
        usage = None

    latency_ms = round((perf_counter() - started) * 1000, 1)
    return PipelineResult(
        verdict=verdict,
        route=route,
        answer=answer,
        citations=citations,
        structured=structured,
        usage=usage,
        latency_ms=latency_ms,
        trace=trace,
    )


async def stream_pipeline(
    pipeline: CompiledPipeline, question: str, context: RequestContext
) -> AsyncIterator[PipelineEvent]:
    """Run the graph, then emit routing, deltas, and a final event (SSE protocol)."""
    started = perf_counter()
    final = await _invoke(pipeline, question, context)

    verdict = final.get("verdict")
    if verdict is None:
        yield ErrorEvent(code="pipeline_error", message="decision graph produced no verdict")
        return
    route = final.get("route_taken")
    trace = final.get("trace", [])
    yield RoutingEvent(verdict=verdict, route=route)

    if verdict is not Verdict.PROCEED:
        latency_ms = round((perf_counter() - started) * 1000, 1)
        yield FinalEvent(
            PipelineResult(
                verdict=verdict,
                route=route,
                answer=final.get("answer") or "",
                citations=final.get("citations") or [],
                structured=final.get("structured"),
                usage=None,
                latency_ms=latency_ms,
                trace=trace,
            )
        )
        return

    tool_result = final.get("tool_result")
    if tool_result is None:
        yield ErrorEvent(code="pipeline_error", message="proceed produced no tool result")
        return

    citations = list(tool_result.citations)
    structured = tool_result.structured
    usage: Usage | None = None
    answer = ""
    async for item in pipeline.synth.stream(question, tool_result, history=_history(final)):
        if isinstance(item, SynthStreamEnd):
            answer = item.result.answer
            citations = item.result.citations
            structured = item.result.structured
            usage = item.result.usage
        else:
            yield DeltaEvent(text=item)

    latency_ms = round((perf_counter() - started) * 1000, 1)
    yield FinalEvent(
        PipelineResult(
            verdict=verdict,
            route=route,
            answer=answer,
            citations=citations,
            structured=structured,
            usage=usage,
            latency_ms=latency_ms,
            trace=trace,
        )
    )
