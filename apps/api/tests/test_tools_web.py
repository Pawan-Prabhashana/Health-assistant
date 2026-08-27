"""Tavily client, fake mode, retries, and the web-search tool."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from sahana_api.config import Settings
from sahana_api.graph.state import RequestContext
from sahana_api.graph.tools import ToolRequest
from sahana_api.tools.tavily import (
    FakeTavilyClient,
    LiveTavilyClient,
    TavilyError,
    WebResult,
    build_tavily_client,
    make_tavily_check,
)
from sahana_api.tools.web import WebSearchTool

_RESULT = WebResult(
    title="Hospital approach",
    url="https://example.org/traffic",
    content="Traffic near the hospital is light this afternoon.",
)


class _SleepRecorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


async def test_fake_mode_returns_canned_results() -> None:
    client = FakeTavilyClient([_RESULT])
    results = await client.search("traffic?", max_results=1)
    assert results == [_RESULT]
    assert client.last_query == "traffic?"


async def test_build_tavily_client_selects_fake() -> None:
    client = build_tavily_client(Settings(tavily_mode="fake"))
    assert isinstance(client, FakeTavilyClient)


async def test_web_tool_cites_real_result_urls() -> None:
    tool = WebSearchTool(FakeTavilyClient([_RESULT]), max_results=5)
    result = await tool.run(ToolRequest("Is there traffic to the hospital?", RequestContext()))

    assert result.metadata["status"] == "grounded"
    assert result.citations == [_RESULT.url]
    assert _RESULT.url in result.payload
    assert "https://invented.example" not in result.payload


async def test_web_tool_empty_is_honest_not_found() -> None:
    tool = WebSearchTool(FakeTavilyClient([]), max_results=5)
    result = await tool.run(ToolRequest("traffic?", RequestContext()))
    assert result.metadata["status"] == "not_found"
    assert result.citations == []


async def test_live_client_retries_transient_then_succeeds() -> None:
    calls = 0

    async def poster(body: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom")
        return {"results": [{"title": "A", "url": "https://example.org/a", "content": "ok"}]}

    sleeper = _SleepRecorder()
    client = LiveTavilyClient(
        api_key="test-key",
        base_url="https://api.tavily.com",
        timeout=1.0,
        max_retries=2,
        sleep=sleeper,
        poster=poster,
    )
    results = await client.search("q", max_results=3)

    assert calls == 2
    assert sleeper.delays == [0.5]
    assert results[0].url == "https://example.org/a"


async def test_live_client_does_not_retry_client_errors() -> None:
    request = httpx.Request("POST", "https://api.tavily.com/search")
    response = httpx.Response(400, request=request)

    async def poster(body: dict[str, Any]) -> dict[str, Any]:
        raise httpx.HTTPStatusError("bad", request=request, response=response)

    sleeper = _SleepRecorder()
    client = LiveTavilyClient(
        api_key="test-key",
        base_url="https://api.tavily.com",
        timeout=1.0,
        max_retries=3,
        sleep=sleeper,
        poster=poster,
    )
    with pytest.raises(TavilyError):
        await client.search("q", max_results=1)
    assert sleeper.delays == []


async def test_live_client_requires_key() -> None:
    client = LiveTavilyClient(
        api_key=None, base_url="https://api.tavily.com", timeout=1.0, max_retries=0
    )
    with pytest.raises(TavilyError):
        await client.search("q", max_results=1)


async def test_tavily_readiness_fake_is_ready() -> None:
    result = await make_tavily_check(Settings(tavily_mode="fake"))()
    assert result.name == "tavily"
    assert result.ok is True
    assert result.detail == "fake mode"


async def test_tavily_readiness_live_missing_key() -> None:
    result = await make_tavily_check(Settings(tavily_mode="live", tavily_api_key=None))()
    assert result.ok is False
    assert result.detail == "missing config: tavily_api_key"


async def test_tavily_readiness_live_configured() -> None:
    result = await make_tavily_check(Settings(tavily_mode="live", tavily_api_key="k"))()
    assert result.ok is True
    assert result.detail is None
