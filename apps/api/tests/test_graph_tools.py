"""Tests for the tool-path registry and stub handlers."""

from __future__ import annotations

import pytest

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import RequestContext
from sahana_api.graph.tools import (
    StubSynthesizer,
    ToolNotRegisteredError,
    ToolRegistry,
    ToolRequest,
    build_stub_registry,
)


async def test_stub_registry_has_a_handler_per_route() -> None:
    registry = build_stub_registry()
    assert registry.routes() == frozenset(Route)

    request = ToolRequest("q", RequestContext())
    for route in Route:
        result = await registry.get(route).run(request)
        assert result.route is route
        assert result.metadata["stub"] is True
        assert result.payload


def test_missing_route_raises() -> None:
    registry = ToolRegistry({})
    with pytest.raises(ToolNotRegisteredError):
        registry.get(Route.RAG)


async def test_stub_synthesizer_is_deterministic() -> None:
    registry = build_stub_registry()
    result = await registry.get(Route.DIRECT).run(ToolRequest("hi", RequestContext()))
    answer = await StubSynthesizer().synthesize("hi", result)
    assert answer.answer.startswith("[direct] ")
