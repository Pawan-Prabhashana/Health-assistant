"""End-to-end decision-graph tests driven by the fake LLM (no keys, no network)."""

from __future__ import annotations

import uuid
from typing import Any

from sahana_api.cag.cache import CagCandidate
from sahana_api.config import Settings
from sahana_api.graph.pipeline import PipelineDeps, build_graph, run_pipeline
from sahana_api.graph.schemas import Route, Verdict
from sahana_api.graph.state import RequestContext
from sahana_api.graph.tools import StubSynthesizer, ToolRegistry, ToolRequest, ToolResult
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry

_IN_SCOPE = {"in_scope": True, "category": "logistics", "reason": "hospital"}
_OFF_TOPIC = {"in_scope": False, "category": "off_topic", "reason": "general knowledge"}


def _route_payload(route: str, confidence: float) -> dict[str, Any]:
    return {
        "route": route,
        "confidence": confidence,
        "reason": "r",
        "needs_patient_identity": False,
    }


class _RecordingTool:
    """A tool handler that records each invocation, to assert tools do/don't fire."""

    def __init__(self, route: Route, log: list[Route]) -> None:
        self.route = route
        self._log = log

    async def run(self, request: ToolRequest) -> ToolResult:
        self._log.append(self.route)
        return ToolResult(route=self.route, payload="recorded", metadata={"stub": True})


def _recording_registry(log: list[Route]) -> ToolRegistry:
    return ToolRegistry({route: _RecordingTool(route, log) for route in Route})


class _StubCag:
    """A stand-in cache exposing only ``peek`` (what the cag node needs)."""

    def __init__(self, candidate: CagCandidate | None) -> None:
        self._candidate = candidate

    async def peek(self, question: str) -> CagCandidate | None:
        return self._candidate


def _deps(
    guardrail: dict[str, Any],
    router: dict[str, Any],
    *,
    cag: Any = None,
    tool_log: list[Route] | None = None,
    settings: Settings | None = None,
) -> PipelineDeps:
    resolved = settings if settings is not None else Settings(llm_mode="fake")
    models = ModelRegistry(
        {
            "guardrail": FakeChatModel(role="guardrail", structured_payload=guardrail),
            "router": FakeChatModel(role="router", structured_payload=router),
            "synth": FakeChatModel(role="synth"),
        }
    )
    tools = _recording_registry(tool_log) if tool_log is not None else _recording_registry([])
    return PipelineDeps(
        models=models, tools=tools, synth=StubSynthesizer(), cag=cag, settings=resolved
    )


async def test_out_of_scope_refuses_and_fires_no_tool() -> None:
    log: list[Route] = []
    # Even with a strong cache candidate, out-of-scope refuses (precedence).
    candidate = CagCandidate(answer="cached", route="rag", score=0.99, expired=False)
    deps = _deps(_OFF_TOPIC, _route_payload("rag", 0.9), cag=_StubCag(candidate), tool_log=log)

    result = await run_pipeline(build_graph(deps), "Weather in Paris?", RequestContext())

    assert result.verdict is Verdict.OUT_OF_SCOPE
    assert result.route is None
    assert result.answer == deps.settings.refusal_message
    assert log == []  # no tool fired


async def test_gated_cache_hit_serves_without_tool() -> None:
    log: list[Route] = []
    candidate = CagCandidate(
        answer="Cached hospital answer.", route="rag", score=0.98, expired=False
    )
    deps = _deps(_IN_SCOPE, _route_payload("rag", 0.9), cag=_StubCag(candidate), tool_log=log)

    result = await run_pipeline(build_graph(deps), "What are the visiting hours?", RequestContext())

    assert result.verdict is Verdict.CACHE_HIT
    assert result.answer == "Cached hospital answer."
    assert log == []  # tools never fire on a cache hit


async def test_proceed_runs_the_routers_tool() -> None:
    log: list[Route] = []
    deps = _deps(_IN_SCOPE, _route_payload("rag", 0.9), cag=_StubCag(None), tool_log=log)

    result = await run_pipeline(build_graph(deps), "Describe skin inspection.", RequestContext())

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.RAG
    assert log == [Route.RAG]
    assert "recorded" in result.answer


async def test_non_allowlisted_cache_route_proceeds_instead() -> None:
    log: list[Route] = []
    # A high-scoring candidate stored under crm must not be served.
    candidate = CagCandidate(answer="secret", route="crm", score=0.99, expired=False)
    deps = _deps(_IN_SCOPE, _route_payload("direct", 0.9), cag=_StubCag(candidate), tool_log=log)

    result = await run_pipeline(build_graph(deps), "Say hello.", RequestContext())

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.DIRECT
    assert log == [Route.DIRECT]


async def test_low_confidence_falls_back_to_default_route() -> None:
    log: list[Route] = []
    deps = _deps(_IN_SCOPE, _route_payload("web_search", 0.2), cag=_StubCag(None), tool_log=log)

    result = await run_pipeline(build_graph(deps), "Ambiguous question.", RequestContext())

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.DIRECT  # documented fallback
    assert log == [Route.DIRECT]


async def test_trace_is_populated_and_pii_free() -> None:
    log: list[Route] = []
    patient_id = uuid.uuid4()
    session_id = uuid.uuid4()
    question = "What are the visiting hours for ward 5?"
    deps = _deps(_IN_SCOPE, _route_payload("rag", 0.9), cag=_StubCag(None), tool_log=log)

    result = await run_pipeline(
        build_graph(deps),
        question,
        RequestContext(session_id=session_id, patient_id=patient_id),
    )

    nodes = {entry.node for entry in result.trace}
    assert nodes == {"guardrail", "router", "cag", "decide", "tool_then_synth"}

    serialized = " ".join(f"{entry.node}:{entry.data}" for entry in result.trace)
    assert str(patient_id) not in serialized
    assert str(session_id) not in serialized
    assert question not in serialized


async def test_parallel_classifiers_fan_in_without_conflict() -> None:
    # The three classifiers write distinct keys and each contribute a trace entry;
    # a clean run with all three present proves the parallel fan-in merged safely.
    deps = _deps(_IN_SCOPE, _route_payload("rag", 0.9), cag=_StubCag(None))

    result = await run_pipeline(build_graph(deps), "A question.", RequestContext())

    classifier_nodes = {
        entry.node for entry in result.trace if entry.node in {"guardrail", "router", "cag"}
    }
    assert classifier_nodes == {"guardrail", "router", "cag"}
