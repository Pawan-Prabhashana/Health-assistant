"""Real tool paths and the non-streaming synthesizer (Phase 5)."""

from __future__ import annotations

from sahana_api.tools.crm import CrmTool
from sahana_api.tools.direct import DirectTool
from sahana_api.tools.grader import RelevanceGrader
from sahana_api.tools.rag import RagTool
from sahana_api.tools.synth import CompletingSynthesizer
from sahana_api.tools.tavily import FakeTavilyClient, TavilyClient, WebResult, build_tavily_client
from sahana_api.tools.web import WebSearchTool
from sahana_api.tools.wiring import build_real_deps, build_tool_registry

__all__ = [
    "CompletingSynthesizer",
    "CrmTool",
    "DirectTool",
    "FakeTavilyClient",
    "RagTool",
    "RelevanceGrader",
    "TavilyClient",
    "WebResult",
    "WebSearchTool",
    "build_real_deps",
    "build_tavily_client",
    "build_tool_registry",
]
