"""Tests for structured output with bounded repair (no network).

The transport is stubbed by overriding ``ProviderClient._create`` to return
scripted completions, so the repair loop is exercised without a live provider.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from pydantic import BaseModel

from sahana_api.llm.base import Completion, Message, StructuredParseError, Usage
from sahana_api.llm.provider import ProviderClient


class _Label(BaseModel):
    label: str


def _usage() -> Usage:
    return Usage(
        prompt_tokens=1,
        completion_tokens=1,
        total_tokens=2,
        estimated_cost_usd=0.0,
        latency_ms=1.0,
    )


def _completion(text: str) -> Completion:
    return Completion(text=text, model="scripted", finish_reason="stop", usage=_usage())


class _ScriptedClient(ProviderClient):
    """A ProviderClient whose completions are scripted, bypassing the transport."""

    def __init__(self, scripted: list[Completion], *, repair_attempts: int = 1) -> None:
        super().__init__(
            role="router",
            model="scripted",
            api_key="test-key",
            base_url="http://localhost",
            prices={},
            timeout=1.0,
            max_retries=0,
            repair_attempts=repair_attempts,
        )
        self._scripted = scripted
        self.calls = 0

    async def _create(
        self,
        messages: Sequence[Message],
        *,
        temperature: float,
        max_tokens: int | None,
        json_mode: bool,
        event: str,
    ) -> Completion:
        self.calls += 1
        return self._scripted.pop(0)


async def test_valid_json_parses_first_try() -> None:
    client = _ScriptedClient([_completion('{"label": "ok"}')])
    result = await client.complete_structured([Message("user", "q")], _Label)
    assert result.value.label == "ok"
    assert client.calls == 1


async def test_code_fenced_json_is_parsed() -> None:
    client = _ScriptedClient([_completion('```json\n{"label": "fenced"}\n```')])
    result = await client.complete_structured([Message("user", "q")], _Label)
    assert result.value.label == "fenced"


async def test_repair_recovers_after_malformed_response() -> None:
    client = _ScriptedClient([_completion("not json at all"), _completion('{"label": "fixed"}')])
    result = await client.complete_structured([Message("user", "q")], _Label)
    assert result.value.label == "fixed"
    assert client.calls == 2


async def test_fails_cleanly_after_repair_bound() -> None:
    client = _ScriptedClient([_completion("nope"), _completion("still not json")])
    with pytest.raises(StructuredParseError):
        await client.complete_structured([Message("user", "q")], _Label)
    assert client.calls == 2
