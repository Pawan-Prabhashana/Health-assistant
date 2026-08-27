"""Opt-in live provider contract tests.

These make one cheap real call per provider to verify connectivity and structured
output. They are marked ``llm_live`` and skip unless the relevant key is present,
so they are never part of the default gate. Run with, e.g.:

    SAHANA_GROQ_API_KEY=... uv run pytest -m llm_live
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from sahana_api.config import Settings
from sahana_api.llm.base import Message, Role
from sahana_api.llm.provider import ProviderClient

pytestmark = pytest.mark.llm_live


class _Sentiment(BaseModel):
    sentiment: str


def _client(role: Role, model: str, api_key: str, base_url: str) -> ProviderClient:
    return ProviderClient(
        role=role,
        model=model,
        api_key=api_key,
        base_url=base_url,
        prices={},
        timeout=30.0,
        max_retries=2,
        repair_attempts=1,
    )


async def test_groq_live_completion_and_structured() -> None:
    settings = Settings()
    if settings.groq_api_key is None:
        pytest.skip("SAHANA_GROQ_API_KEY not set")

    client = _client("router", settings.router_model, settings.groq_api_key, settings.groq_base_url)
    try:
        completion = await client.complete(
            [Message("user", "Reply with the single word: pong")], max_tokens=16
        )
        assert completion.text
        assert completion.usage.total_tokens > 0

        structured = await client.complete_structured(
            [Message("user", "Classify the sentiment of 'I love this hospital'.")],
            _Sentiment,
            max_tokens=64,
        )
        assert structured.value.sentiment
    finally:
        await client.aclose()


async def test_openrouter_live_completion() -> None:
    settings = Settings()
    if settings.openrouter_api_key is None:
        pytest.skip("SAHANA_OPENROUTER_API_KEY not set")

    client = _client(
        "synth", settings.synth_model, settings.openrouter_api_key, settings.openrouter_base_url
    )
    try:
        completion = await client.complete(
            [Message("user", "Reply with the single word: pong")], max_tokens=16
        )
        assert completion.text
    finally:
        await client.aclose()
