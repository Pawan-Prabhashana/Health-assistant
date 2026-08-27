"""The four real tool routes through ``run_pipeline``, with no graph or decide() change."""

from __future__ import annotations

from typing import Any

from sahana_api.config import Settings
from sahana_api.graph.pipeline import PipelineDeps, build_graph, run_pipeline
from sahana_api.graph.schemas import Route, Verdict
from sahana_api.graph.state import RequestContext
from sahana_api.kb.retriever import ScoredChunk
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.registry import ModelRegistry
from sahana_api.tools.crm import CrmTool
from sahana_api.tools.direct import DirectTool
from sahana_api.tools.prompts import IDENTIFY_REQUIRED, MEDICAL_SAFETY_POSTURE, NOT_FOUND_MESSAGE
from sahana_api.tools.rag import RagTool
from sahana_api.tools.tavily import FakeTavilyClient, WebResult
from sahana_api.tools.web import WebSearchTool
from sahana_api.tools.wiring import build_real_deps, build_tool_registry

_IN_SCOPE = {"in_scope": True, "category": "logistics", "reason": "hospital"}
_SKIN = ScoredChunk(
    score=0.9,
    doc_id="skin",
    title="Skin Inspection Procedure",
    source="procedures/skin-inspection",
    section="Steps",
    chunk_index=0,
    text="Obtain consent, then inspect the skin systematically.",
)
_WEB = WebResult(
    title="Traffic",
    url="https://example.org/traffic",
    content="Traffic near the hospital is light this afternoon.",
)


class _FakeRetriever:
    def __init__(self, chunks: list[ScoredChunk]) -> None:
        self.chunks = chunks

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        return self.chunks[:top_k]


def _route_payload(route: str, *, identity: bool = False) -> dict[str, Any]:
    return {
        "route": route,
        "confidence": 0.9,
        "reason": "r",
        "needs_patient_identity": identity,
    }


def _deps(
    *,
    router: dict[str, Any],
    synth_text: str,
    chunks: list[ScoredChunk] | None = None,
    web_results: list[WebResult] | None = None,
    grades: list[dict[str, Any]] | None = None,
) -> PipelineDeps:
    settings = Settings(llm_mode="fake", tavily_mode="fake", kb_embedder="local")
    models = ModelRegistry(
        {
            "guardrail": FakeChatModel(
                role="guardrail",
                structured_by_schema={
                    "GuardrailVerdict": _IN_SCOPE,
                    "RelevanceGrades": {
                        "grades": grades if grades is not None else [{"index": 0, "relevant": True}]
                    },
                },
            ),
            "router": FakeChatModel(role="router", structured_payload=router),
            "synth": FakeChatModel(role="synth", text=synth_text),
        }
    )
    tavily = FakeTavilyClient(web_results if web_results is not None else [_WEB])
    return build_real_deps(
        settings,
        models,
        None,
        session_provider=None,
        retriever=_FakeRetriever(chunks if chunks is not None else [_SKIN]),
        tavily=tavily,
    )


async def test_direct_route_returns_concierge_reply() -> None:
    deps = _deps(router=_route_payload("direct"), synth_text="Hello, welcome to the hospital.")
    result = await run_pipeline(build_graph(deps), "Hey there.", RequestContext())

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.DIRECT
    assert result.answer == "Hello, welcome to the hospital."
    synth = deps.models.get_model("synth")
    assert isinstance(synth, FakeChatModel)
    assert MEDICAL_SAFETY_POSTURE in synth.complete_calls[0][0].content


async def test_web_route_cites_tavily_urls() -> None:
    deps = _deps(
        router=_route_payload("web_search"),
        synth_text="Traffic is light this afternoon.",
        web_results=[_WEB],
    )
    result = await run_pipeline(
        build_graph(deps), "Is there traffic to the hospital?", RequestContext()
    )

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.WEB_SEARCH
    assert result.citations == [_WEB.url]
    assert "light this afternoon" in result.answer


async def test_rag_route_cites_real_kb_source() -> None:
    deps = _deps(
        router=_route_payload("rag"),
        synth_text="Obtain consent, then inspect the skin systematically.",
        chunks=[_SKIN],
        grades=[{"index": 0, "relevant": True}],
    )
    result = await run_pipeline(
        build_graph(deps), "What is the procedure for a skin inspection?", RequestContext()
    )

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.RAG
    assert any("procedures/skin-inspection" in citation for citation in result.citations)
    assert "consent" in result.answer


async def test_crm_identity_gate_refuses_unidentified_caller() -> None:
    deps = _deps(router=_route_payload("crm", identity=True), synth_text="should not run")
    result = await run_pipeline(
        build_graph(deps), "Do I have an appointment today?", RequestContext()
    )

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.CRM
    assert result.answer == IDENTIFY_REQUIRED
    assert result.structured is None
    synth = deps.models.get_model("synth")
    assert isinstance(synth, FakeChatModel)
    assert synth.complete_calls == []


async def test_crag_corrective_fallback_fires_through_pipeline() -> None:
    deps = _deps(
        router=_route_payload("rag"),
        synth_text="Traffic near the hospital is light this afternoon.",
        chunks=[_SKIN],
        grades=[{"index": 0, "relevant": False}],
        web_results=[_WEB],
    )
    result = await run_pipeline(
        build_graph(deps), "Is there traffic to the hospital?", RequestContext()
    )

    assert result.verdict is Verdict.PROCEED
    assert result.route is Route.RAG
    assert result.citations == [_WEB.url]


async def test_crag_both_empty_is_honest_not_found() -> None:
    deps = _deps(
        router=_route_payload("rag"),
        synth_text="should not run",
        chunks=[],
        grades=[],
        web_results=[],
    )
    result = await run_pipeline(build_graph(deps), "Unknown protocol?", RequestContext())
    assert result.answer == NOT_FOUND_MESSAGE
    assert result.citations == []


async def test_registry_swap_registers_real_tools() -> None:
    settings = Settings(llm_mode="fake", tavily_mode="fake")
    models = ModelRegistry(
        {
            "guardrail": FakeChatModel(role="guardrail"),
            "router": FakeChatModel(role="router"),
            "synth": FakeChatModel(role="synth"),
        }
    )
    registry = build_tool_registry(
        settings=settings,
        models=models,
        session_provider=None,
        retriever=None,
        tavily=FakeTavilyClient(),
    )
    assert isinstance(registry.get(Route.CRM), CrmTool)
    assert isinstance(registry.get(Route.RAG), RagTool)
    assert isinstance(registry.get(Route.DIRECT), DirectTool)
    assert isinstance(registry.get(Route.WEB_SEARCH), WebSearchTool)
    assert registry.routes() == frozenset(Route)
