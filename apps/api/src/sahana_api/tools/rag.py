"""RAG tool path with CRAG relevance grading and a corrective web fallback.

Retrieval returns the top-k chunks. An optional per-embedder score gate (from
config, never a hardcoded constant) drops obviously-unrelated neighbours because
the local MiniLM and OpenAI embedders score on different scales. A cheap LLM then
grades the survivors for actual relevance in one batched call. Relevance — not
raw similarity — decides usefulness. If too few chunks grade relevant, the
corrective action is a web-search fallback (when enabled), then an honest
not-found. See ADR 0011.
"""

from __future__ import annotations

from typing import Protocol

from sahana_api.config import Settings
from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import ToolRequest, ToolResult
from sahana_api.kb.retriever import ScoredChunk
from sahana_api.logging import get_logger
from sahana_api.tools.grader import RelevanceGrader
from sahana_api.tools.prompts import NOT_FOUND_MESSAGE
from sahana_api.tools.web import WebSearchTool

_logger = get_logger("sahana_api.tools.rag")


class Retriever(Protocol):
    """The search surface the RAG tool needs (satisfied by ``KnowledgeRetriever``)."""

    async def search(self, query: str, top_k: int) -> list[ScoredChunk]: ...


def chunk_citation(chunk: ScoredChunk) -> str:
    """Stable citation label tracing to a retrieved KB chunk's title and source."""
    return f"{chunk.title} [{chunk.source}]"


def _score_gate(settings: Settings) -> float:
    """Return the configured score floor for the active KB embedder (0 disables)."""
    if settings.kb_embedder == "openai":
        return settings.rag_score_gate_openai
    return settings.rag_score_gate_local


def _apply_score_gate(chunks: list[ScoredChunk], gate: float) -> list[ScoredChunk]:
    if gate <= 0.0:
        return chunks
    return [chunk for chunk in chunks if chunk.score >= gate]


def _render_context(chunks: list[ScoredChunk]) -> str:
    return "\n\n".join(f"[{chunk_citation(chunk)}]\n{chunk.text}" for chunk in chunks)


def _not_found(corrective: bool) -> ToolResult:
    return ToolResult(
        route=Route.RAG,
        payload=NOT_FOUND_MESSAGE,
        metadata={"status": "not_found", "corrective_fallback": corrective},
    )


class RagTool:
    """Retrieves, grades, and (when needed) falls back to web search."""

    route = Route.RAG

    def __init__(
        self,
        retriever: Retriever | None,
        grader: RelevanceGrader,
        web: WebSearchTool,
        settings: Settings,
    ) -> None:
        self._retriever = retriever
        self._grader = grader
        self._web = web
        self._settings = settings

    async def run(self, request: ToolRequest) -> ToolResult:
        chunks = await self._retrieve(request.question)
        gated = _apply_score_gate(chunks, _score_gate(self._settings))
        relevant = await self._relevant(request.question, gated)

        if len(relevant) >= self._settings.crag_min_relevant:
            return ToolResult(
                route=Route.RAG,
                payload=_render_context(relevant),
                citations=[chunk_citation(chunk) for chunk in relevant],
                metadata={"status": "grounded", "source": "kb"},
            )

        if self._settings.crag_corrective_fallback:
            _logger.info("rag.corrective_fallback", retrieved=len(chunks), gated=len(gated))
            web_result = await self._web.run(request)
            if web_result.metadata.get("status") == "grounded" and web_result.citations:
                return ToolResult(
                    route=Route.RAG,
                    payload=web_result.payload,
                    citations=web_result.citations,
                    metadata={
                        "status": "grounded",
                        "source": "web",
                        "corrective_fallback": True,
                    },
                )
            return _not_found(corrective=True)

        return _not_found(corrective=False)

    async def _retrieve(self, question: str) -> list[ScoredChunk]:
        if self._retriever is None:
            return []
        return await self._retriever.search(question, self._settings.rag_top_k)

    async def _relevant(self, question: str, chunks: list[ScoredChunk]) -> list[ScoredChunk]:
        if not chunks:
            return []
        flags = await self._grader.grade(question, chunks)
        return [chunk for chunk, keep in zip(chunks, flags, strict=True) if keep]
