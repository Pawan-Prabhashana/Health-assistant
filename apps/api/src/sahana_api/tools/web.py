"""Web-search tool path (Tavily)."""

from __future__ import annotations

from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import ToolRequest, ToolResult
from sahana_api.logging import get_logger
from sahana_api.tools.tavily import TavilyClient, WebResult

_logger = get_logger("sahana_api.tools.web")


def _render_context(results: list[WebResult]) -> str:
    """Render results into a labelled context block the synthesizer grounds on."""
    return "\n\n".join(f"[{result.url}] {result.title}: {result.content}" for result in results)


class WebSearchTool:
    """Searches the web and returns grounded context with real result URLs."""

    route = Route.WEB_SEARCH

    def __init__(self, client: TavilyClient, max_results: int) -> None:
        self._client = client
        self._max_results = max_results

    async def run(self, request: ToolRequest) -> ToolResult:
        try:
            results = await self._client.search(request.question, max_results=self._max_results)
        except Exception as exc:  # any search failure degrades to an honest not-found
            _logger.warning("web.search.failed", error=type(exc).__name__)
            results = []

        if not results:
            return ToolResult(route=Route.WEB_SEARCH, payload="", metadata={"status": "not_found"})

        return ToolResult(
            route=Route.WEB_SEARCH,
            payload=_render_context(results),
            citations=[result.url for result in results],
            metadata={"status": "grounded", "source": "web"},
        )
