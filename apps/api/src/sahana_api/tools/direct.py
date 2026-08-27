"""Direct concierge tool path.

The lowest-latency proceed path: no external tool. It carries no context; the
synthesizer produces the concierge reply from the question using the concierge
system prompt.
"""

from __future__ import annotations

from sahana_api.graph.schemas import Route
from sahana_api.graph.tools import ToolRequest, ToolResult


class DirectTool:
    """Produces an empty-context result; the synthesizer writes the concierge reply."""

    route = Route.DIRECT

    async def run(self, request: ToolRequest) -> ToolResult:
        return ToolResult(route=Route.DIRECT, payload="", metadata={"status": "direct"})
