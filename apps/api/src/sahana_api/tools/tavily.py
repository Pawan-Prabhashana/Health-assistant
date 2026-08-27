"""Tavily web-search client behind a small typed abstraction.

A thin typed httpx wrapper is used rather than the Tavily SDK: httpx is already a
dependency, the request/response shape is small, and it keeps the image slim (see
ADR 0011). A ``fake`` mode mirrors the LLM fake so the suite runs without a key.
The client applies a per-attempt timeout and bounded retries for transient errors.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from sahana_api.config import Settings
from sahana_api.logging import get_logger
from sahana_api.readiness import DependencyCheck
from sahana_api.schemas.health import Check

_logger = get_logger("sahana_api.tools.tavily")

Sleeper = Callable[[float], Awaitable[None]]
Poster = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class TavilyError(RuntimeError):
    """Raised when a Tavily search fails after retries, or is misconfigured."""


@dataclass(frozen=True)
class WebResult:
    """One web search result."""

    title: str
    url: str
    content: str


class TavilyClient(Protocol):
    """Searches the web and returns typed results."""

    async def search(self, query: str, *, max_results: int) -> list[WebResult]: ...


class FakeTavilyClient:
    """A deterministic client returning canned results (no network)."""

    def __init__(self, results: list[WebResult] | None = None) -> None:
        self._results = (
            results
            if results is not None
            else [
                WebResult(
                    title="Route to the hospital",
                    url="https://example.org/traffic",
                    content="Traffic near the hospital is light this afternoon.",
                )
            ]
        )
        self.last_query: str | None = None

    async def search(self, query: str, *, max_results: int) -> list[WebResult]:
        self.last_query = query
        return self._results[:max_results]


class LiveTavilyClient:
    """Calls the Tavily search API over httpx with a timeout and bounded retries."""

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        timeout: float,
        max_retries: int,
        sleep: Sleeper = asyncio.sleep,
        poster: Poster | None = None,
    ) -> None:
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/search"
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep
        self._poster = poster

    async def search(self, query: str, *, max_results: int) -> list[WebResult]:
        if self._api_key is None:
            raise TavilyError("SAHANA_TAVILY_API_KEY is not configured")

        body = {"api_key": self._api_key, "query": query, "max_results": max_results}
        last_error: BaseException | None = None
        for attempt in range(self._max_retries + 1):
            try:
                data = await asyncio.wait_for(self._post(body), timeout=self._timeout)
            except (TimeoutError, httpx.TransportError) as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 and exc.response.status_code != 429:
                    raise TavilyError("tavily request failed") from exc
                last_error = exc
            else:
                return _parse_results(data)
            if attempt < self._max_retries:
                await self._sleep(0.5 * (attempt + 1))
        raise TavilyError("tavily search failed after retries") from last_error

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        if self._poster is not None:
            return await self._poster(body)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url, json=body)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            return payload


def _parse_results(data: dict[str, Any]) -> list[WebResult]:
    """Map the Tavily response into typed results, tolerating missing fields."""
    results: list[WebResult] = []
    for item in data.get("results", []):
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        results.append(
            WebResult(
                title=str(item.get("title", "")),
                url=url,
                content=str(item.get("content", "")),
            )
        )
    return results


def build_tavily_client(settings: Settings) -> TavilyClient:
    """Return the fake or live Tavily client per ``tavily_mode``."""
    if settings.tavily_mode == "fake":
        return FakeTavilyClient()
    return LiveTavilyClient(
        api_key=settings.tavily_api_key,
        base_url=settings.tavily_base_url,
        timeout=settings.tavily_timeout_seconds,
        max_retries=settings.tavily_max_retries,
    )


def make_tavily_check(settings: Settings) -> DependencyCheck:
    """Config-only readiness for the Tavily capability (no live call)."""

    async def check() -> Check:
        if settings.tavily_mode == "fake":
            return Check(name="tavily", ok=True, detail="fake mode")
        if settings.tavily_api_key is None:
            return Check(name="tavily", ok=False, detail="missing config: tavily_api_key")
        return Check(name="tavily", ok=True, detail=None)

    return check
