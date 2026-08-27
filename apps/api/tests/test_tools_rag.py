"""RAG/CRAG tool: grading, corrective web fallback, honest not-found, real citations."""

from __future__ import annotations

from pathlib import Path

import pytest
from qdrant_client import AsyncQdrantClient

from sahana_api.config import Settings
from sahana_api.embeddings.local import LocalEmbedder
from sahana_api.graph.state import RequestContext
from sahana_api.graph.tools import ToolRequest
from sahana_api.kb.chunking import TokenChunker
from sahana_api.kb.ingest import ingest_knowledge_base
from sahana_api.kb.retriever import KnowledgeRetriever, ScoredChunk
from sahana_api.llm.fake import FakeChatModel
from sahana_api.tools.grader import RelevanceGrader
from sahana_api.tools.prompts import NOT_FOUND_MESSAGE
from sahana_api.tools.rag import RagTool, chunk_citation
from sahana_api.tools.tavily import FakeTavilyClient, WebResult
from sahana_api.tools.web import WebSearchTool

_QUESTION = "What is the procedure for a skin inspection?"
_SKIN = ScoredChunk(
    score=0.8,
    doc_id="skin",
    title="Skin Inspection Procedure",
    source="procedures/skin-inspection",
    section="Procedure Steps",
    chunk_index=0,
    text="Explain the inspection, obtain consent, and inspect skin systematically.",
)
_IRRELEVANT = ScoredChunk(
    score=0.7,
    doc_id="park",
    title="Visitor Parking",
    source="visiting-hours-and-faqs",
    section="Parking",
    chunk_index=0,
    text="Visitor parking is behind the west wing.",
)
_WEB = WebResult(
    title="Hospital traffic",
    url="https://example.org/traffic",
    content="Traffic near the hospital is light this afternoon.",
)


class _FakeRetriever:
    def __init__(self, chunks: list[ScoredChunk]) -> None:
        self.chunks = chunks

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]:
        return self.chunks[:top_k]


def _settings(
    *,
    rag_score_gate_local: float = 0.3,
    rag_score_gate_openai: float = 0.2,
) -> Settings:
    return Settings(
        llm_mode="fake",
        tavily_mode="fake",
        kb_embedder="local",
        rag_score_gate_local=rag_score_gate_local,
        rag_score_gate_openai=rag_score_gate_openai,
    )


def _tool(
    chunks: list[ScoredChunk],
    grades: list[dict[str, object]],
    *,
    web_results: list[WebResult] | None = None,
    settings: Settings | None = None,
) -> RagTool:
    grader = RelevanceGrader(FakeChatModel(role="guardrail", structured_payload={"grades": grades}))
    web = WebSearchTool(FakeTavilyClient(web_results if web_results is not None else [_WEB]), 5)
    return RagTool(_FakeRetriever(chunks), grader, web, settings or _settings())


async def test_relevant_chunks_produce_kb_citations() -> None:
    result = await _tool([_SKIN], [{"index": 0, "relevant": True}]).run(
        ToolRequest(_QUESTION, RequestContext())
    )

    assert result.metadata["status"] == "grounded"
    assert result.metadata["source"] == "kb"
    assert result.citations == [chunk_citation(_SKIN)]
    assert "procedures/skin-inspection" in result.citations[0]
    assert "consent" in result.payload
    assert "https://invented.example" not in result.payload


async def test_irrelevant_triggers_corrective_web_fallback() -> None:
    result = await _tool(
        [_IRRELEVANT],
        [{"index": 0, "relevant": False}],
        web_results=[_WEB],
    ).run(ToolRequest("Is there traffic to the hospital?", RequestContext()))

    assert result.metadata["corrective_fallback"] is True
    assert result.metadata["source"] == "web"
    assert result.citations == [_WEB.url]
    assert _WEB.url in result.payload


async def test_both_empty_returns_honest_not_found() -> None:
    result = await _tool([], [], web_results=[]).run(ToolRequest(_QUESTION, RequestContext()))

    assert result.metadata["status"] == "not_found"
    assert result.payload == NOT_FOUND_MESSAGE
    assert result.citations == []


async def test_score_gate_uses_per_embedder_config_not_a_constant() -> None:
    low = ScoredChunk(
        score=0.1,
        doc_id="weak",
        title="Unrelated",
        source="other",
        section="x",
        chunk_index=0,
        text="Completely unrelated passage.",
    )
    settings = _settings(rag_score_gate_local=0.5, rag_score_gate_openai=0.01)
    result = await _tool(
        [low],
        [{"index": 0, "relevant": True}],
        web_results=[],
        settings=settings,
    ).run(ToolRequest(_QUESTION, RequestContext()))

    # The local gate dropped the weak neighbour before grading, so the relevant
    # grade never applied and both-empty yields not-found.
    assert result.metadata["status"] == "not_found"
    assert result.citations == []


async def test_no_fabricated_citations_on_web_fallback() -> None:
    result = await _tool(
        [_IRRELEVANT],
        [{"index": 0, "relevant": False}],
        web_results=[_WEB],
    ).run(ToolRequest("traffic?", RequestContext()))
    assert all(citation == _WEB.url for citation in result.citations)


@pytest.mark.qdrant
async def test_real_kb_citation_traces_to_ingested_source(
    qdrant_client: AsyncQdrantClient,
    collection_name: str,
    local_embedder: LocalEmbedder,
    token_chunker: TokenChunker,
    kb_root: Path,
) -> None:
    await ingest_knowledge_base(
        client=qdrant_client,
        collection=collection_name,
        embedder=local_embedder,
        chunker=token_chunker,
        root=kb_root,
    )
    retriever = KnowledgeRetriever(qdrant_client, collection_name, local_embedder)
    retrieved = await retriever.search(_QUESTION, top_k=4)
    assert retrieved
    grades = [{"index": index, "relevant": True} for index in range(len(retrieved))]
    web = WebSearchTool(FakeTavilyClient([]), 5)
    tool = RagTool(
        retriever,
        RelevanceGrader(FakeChatModel(structured_payload={"grades": grades})),
        web,
        _settings(),
    )

    result = await tool.run(ToolRequest(_QUESTION, RequestContext()))

    assert result.metadata["source"] == "kb"
    assert result.citations
    assert any("skin-inspection" in citation for citation in result.citations)
    for citation in result.citations:
        assert any(chunk_citation(chunk) == citation for chunk in retrieved), citation
