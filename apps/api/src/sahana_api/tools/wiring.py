"""Assemble the real tool registry and pipeline deps (the Phase 5 registration swap)."""

from __future__ import annotations

from sahana_api.cag.cache import CagCache
from sahana_api.config import Settings
from sahana_api.graph.pipeline import PipelineDeps
from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import ToolPath, ToolRegistry
from sahana_api.llm.base import ChatModel, ProviderNotConfiguredError, Role
from sahana_api.llm.registry import ModelRegistry
from sahana_api.tools.crm import CrmTool, SessionProvider
from sahana_api.tools.direct import DirectTool
from sahana_api.tools.grader import RelevanceGrader
from sahana_api.tools.rag import RagTool, Retriever
from sahana_api.tools.synth import CompletingSynthesizer
from sahana_api.tools.tavily import TavilyClient
from sahana_api.tools.web import WebSearchTool


def _optional_model(models: ModelRegistry, role: Role) -> ChatModel | None:
    """Return the model for ``role``, or ``None`` when that role is unconfigured."""
    try:
        return models.get_model(role)
    except ProviderNotConfiguredError:
        return None


def build_tool_registry(
    *,
    settings: Settings,
    models: ModelRegistry,
    session_provider: SessionProvider | None,
    retriever: Retriever | None,
    tavily: TavilyClient,
) -> ToolRegistry:
    """Return a registry of the four real tool paths, keyed by route."""
    web = WebSearchTool(tavily, settings.tavily_max_results)
    rag = RagTool(
        retriever=retriever,
        grader=RelevanceGrader(_optional_model(models, settings.crag_grader_role)),
        web=web,
        settings=settings,
    )
    handlers: dict[Route, ToolPath] = {
        Route.CRM: CrmTool(session_provider),
        Route.RAG: rag,
        Route.DIRECT: DirectTool(),
        Route.WEB_SEARCH: web,
    }
    return ToolRegistry(handlers)


def build_real_deps(
    settings: Settings,
    models: ModelRegistry,
    cag: CagCache | None,
    *,
    session_provider: SessionProvider | None,
    retriever: Retriever | None,
    tavily: TavilyClient,
) -> PipelineDeps:
    """Assemble deps with the real tools and the non-streaming synthesizer."""
    return PipelineDeps(
        models=models,
        tools=build_tool_registry(
            settings=settings,
            models=models,
            session_provider=session_provider,
            retriever=retriever,
            tavily=tavily,
        ),
        synth=CompletingSynthesizer(_optional_model(models, "synth")),
        cag=cag,
        settings=settings,
        session_provider=session_provider,
    )
