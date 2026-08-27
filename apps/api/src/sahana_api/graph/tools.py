"""Tool-path registry, result type, and Phase 4 stub handlers.

The ``ToolPath`` registry is the seam between the graph and the tool paths. In
Phase 4 it is populated with deterministic, typed stub handlers — one per route —
that echo the route and a canned payload. Phase 5 replaces the handlers with the
real CRM/RAG/direct/web-search tools, and Phase 6 replaces the stub synthesizer
with the streamed model, by swapping registrations, not by touching the graph.
These stubs are real implementations behind the same interface, not placeholders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import RequestContext


class ToolNotRegisteredError(KeyError):
    """Raised when no handler is registered for a requested route."""


@dataclass(frozen=True)
class ToolRequest:
    """Input to a tool path."""

    question: str
    context: RequestContext


@dataclass(frozen=True)
class ToolResult:
    """The typed output of a tool path, consumed by the synthesizer."""

    route: Route
    payload: str
    citations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ToolPath(Protocol):
    """A handler for one route. Phase 5 tools implement this same interface."""

    route: Route

    async def run(self, request: ToolRequest) -> ToolResult: ...


class Synthesizer(Protocol):
    """Turns a tool result into a final answer. Phase 6 streams the real model."""

    async def synthesize(self, question: str, result: ToolResult) -> str: ...


@dataclass(frozen=True)
class ToolRegistry:
    """Immutable route → handler mapping."""

    handlers: dict[Route, ToolPath]

    def get(self, route: Route) -> ToolPath:
        """Return the handler for ``route``.

        :raises ToolNotRegisteredError: if no handler is registered.
        """
        try:
            return self.handlers[route]
        except KeyError as exc:
            raise ToolNotRegisteredError(route) from exc

    def routes(self) -> frozenset[Route]:
        """Return the routes with a registered handler."""
        return frozenset(self.handlers)


class _StubToolPath:
    """A deterministic stub handler that echoes its route and a canned payload."""

    def __init__(self, route: Route, payload: str) -> None:
        self.route = route
        self._payload = payload

    async def run(self, request: ToolRequest) -> ToolResult:
        return ToolResult(route=self.route, payload=self._payload, metadata={"stub": True})


class StubSynthesizer:
    """A deterministic stub synthesizer. Phase 6 replaces it with the streamed model."""

    async def synthesize(self, question: str, result: ToolResult) -> str:
        return f"[{result.route.value}] {result.payload}"


_STUB_PAYLOADS: dict[Route, str] = {
    Route.CRM: "Stub CRM lookup: patient record and next appointment would appear here.",
    Route.RAG: "Stub RAG answer: a grounded answer from the knowledge base would appear here.",
    Route.DIRECT: "Stub direct reply: a concierge answer would appear here.",
    Route.WEB_SEARCH: "Stub web search: a summarized web result would appear here.",
}


def build_stub_registry() -> ToolRegistry:
    """Return a registry populated with one deterministic stub handler per route."""
    handlers: dict[Route, ToolPath] = {
        route: _StubToolPath(route, payload) for route, payload in _STUB_PAYLOADS.items()
    }
    return ToolRegistry(handlers)
