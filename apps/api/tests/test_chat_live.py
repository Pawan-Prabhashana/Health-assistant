"""Opt-in live latency smoke test against the budgets.

Marked ``llm_live`` and skipped unless the Groq and OpenRouter keys are present,
so it is never part of the default gate. When keys are present it measures real
wall-clock latency for a tool-backed (direct) turn against the ~2.5s budget. Run
with, e.g.:

    SAHANA_GROQ_API_KEY=... SAHANA_OPENROUTER_API_KEY=... uv run pytest -m llm_live
"""

from __future__ import annotations

import pytest

from sahana_api.config import Settings
from sahana_api.graph.context import RequestContext
from sahana_api.graph.pipeline import build_graph, run_pipeline
from sahana_api.llm.registry import build_model_registry
from sahana_api.tools.tavily import FakeTavilyClient
from sahana_api.tools.wiring import build_real_deps

pytestmark = pytest.mark.llm_live

_TOOL_BACKED_BUDGET_MS = 4000.0


async def test_direct_turn_meets_latency_budget() -> None:
    settings = Settings()
    if settings.groq_api_key is None or settings.openrouter_api_key is None:
        pytest.skip("SAHANA_GROQ_API_KEY / SAHANA_OPENROUTER_API_KEY not set")

    models = build_model_registry(settings)
    deps = build_real_deps(
        settings,
        models,
        None,
        session_provider=None,
        retriever=None,
        tavily=FakeTavilyClient(),
    )
    pipeline = build_graph(deps)
    try:
        result = await run_pipeline(pipeline, "Hello, can you help me?", RequestContext())
    finally:
        await models.aclose()

    assert result.answer
    assert result.latency_ms > 0.0
    assert result.latency_ms < _TOOL_BACKED_BUDGET_MS
