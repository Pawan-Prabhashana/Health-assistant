"""Tool-path registry, result type, and test-only stub handlers.

The ``ToolPath`` registry is the seam between the graph and the tool paths. Phase
5 registers the real CRM/RAG/direct/web-search tools; Phase 6 swaps the
completing synthesizer for the streamed model. Both swaps change registrations,
not the graph. The stubs remain as deterministic stand-ins for graph-shape tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from sahana_api.graph.context import RequestContext, StructuredTable
from sahana_api.graph.schemas import Route
from sahana_api.llm.base import Message, Usage


class ToolNotRegisteredError(KeyError):
    """Raised when no handler is registered for a requested route."""


@dataclass(frozen=True)
class ToolRequest:
    """Input to a tool path."""

    question: str
    context: RequestContext


@dataclass(frozen=True)
class ToolResult:
    """The typed output of a tool path, consumed by the synthesizer.

    ``payload`` is the context text (or authoritative rendering) the synthesizer
    grounds on; ``citations`` are the real sources the tool actually retrieved (the
    synthesizer never invents citations); ``structured`` carries an authoritative
    table (CRM) the frontend renders verbatim; ``metadata`` carries a ``status``
    the synthesizer and trace read (e.g. ``grounded``, ``not_found``,
    ``identify_required``).
    """

    route: Route
    payload: str
    citations: list[str] = field(default_factory=list)
    structured: StructuredTable | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SynthesisResult:
    """The synthesizer's typed output: the answer plus what it grounded on."""

    answer: str
    citations: list[str] = field(default_factory=list)
    structured: StructuredTable | None = None
    usage: Usage | None = None


@dataclass(frozen=True)
class SynthStreamEnd:
    """Terminal item of a synth stream, carrying the completed result."""

    result: SynthesisResult


@runtime_checkable
class ToolPath(Protocol):
    """A handler for one route. Phase 5 tools implement this same interface."""

    route: Route

    async def run(self, request: ToolRequest) -> ToolResult: ...


class Synthesizer(Protocol):
    """Turns a tool result into a final answer, optionally with recalled history."""

    async def synthesize(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> SynthesisResult: ...

    def stream(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> AsyncIterator[str | SynthStreamEnd]: ...


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
    """A deterministic stub synthesizer. Phase 5 replaces it with the real model."""

    async def synthesize(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> SynthesisResult:
        return SynthesisResult(
            answer=f"[{result.route.value}] {result.payload}",
            citations=result.citations,
            structured=result.structured,
        )

    async def stream(
        self,
        question: str,
        result: ToolResult,
        *,
        history: Sequence[Message] | None = None,
    ) -> AsyncIterator[str | SynthStreamEnd]:
        yield SynthStreamEnd(await self.synthesize(question, result, history=history))


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
