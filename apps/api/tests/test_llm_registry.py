"""Tests for the role registry, factory, cost estimation, and LLM readiness."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from sahana_api.config import ModelPrice, Settings
from sahana_api.llm.base import ProviderNotConfiguredError
from sahana_api.llm.fake import FakeChatModel
from sahana_api.llm.health import make_llm_check
from sahana_api.llm.provider import ProviderClient
from sahana_api.llm.registry import ModelRegistry, build_model_registry
from sahana_api.llm.usage import estimate_cost
from sahana_api.main import create_app

_ROLES = ("guardrail", "router", "synth")


def test_default_model_ids_and_base_urls() -> None:
    settings = Settings()
    assert settings.guardrail_model == "openai/gpt-oss-20b"
    assert settings.router_model == "openai/gpt-oss-120b"
    assert settings.synth_model == "google/gemini-2.5-flash"
    assert settings.groq_base_url == "https://api.groq.com/openai/v1"
    assert settings.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert settings.rag_top_k == 4
    assert settings.crag_grader_role == "guardrail"
    assert settings.rag_score_gate_openai == 0.2
    assert settings.rag_score_gate_local == 0.3
    assert settings.tavily_mode == "live"


def test_fake_registry_serves_every_role() -> None:
    registry = build_model_registry(Settings(llm_mode="fake"))
    for role in _ROLES:
        model = registry.get_model(role)
        assert isinstance(model, FakeChatModel)
        assert model.model == f"fake-{role}"


def test_missing_role_raises() -> None:
    registry = ModelRegistry({})
    with pytest.raises(ProviderNotConfiguredError):
        registry.get_model("guardrail")


def test_live_registry_builds_only_configured_roles() -> None:
    # Groq key present, OpenRouter key absent → synth is unavailable.
    settings = Settings(llm_mode="live", groq_api_key="groq-key", openrouter_api_key=None)
    registry = build_model_registry(settings)

    assert registry.configured_roles() == frozenset({"guardrail", "router"})
    guardrail = registry.get_model("guardrail")
    assert isinstance(guardrail, ProviderClient)
    assert guardrail.model == settings.guardrail_model


async def test_live_registry_closes_clients() -> None:
    settings = Settings(llm_mode="live", groq_api_key="groq-key", openrouter_api_key="or-key")
    registry = build_model_registry(settings)
    assert registry.configured_roles() == frozenset(_ROLES)
    await registry.aclose()


def test_cost_estimation_math() -> None:
    prices = {"m": ModelPrice(input_per_1m=1.0, output_per_1m=2.0)}
    # 1,000,000 input @ $1 + 500,000 output @ $2 = $1.00 + $1.00 = $2.00
    assert estimate_cost(prices, "m", 1_000_000, 500_000) == 2.0
    # Unknown models cost nothing (estimation only).
    assert estimate_cost(prices, "unknown", 100, 100) == 0.0


async def test_llm_check_fake_is_ready() -> None:
    result = await make_llm_check(Settings(llm_mode="fake"))()
    assert result.name == "llm"
    assert result.ok is True
    assert result.detail == "fake mode"


async def test_llm_check_reports_missing_config() -> None:
    result = await make_llm_check(
        Settings(llm_mode="live", groq_api_key=None, openrouter_api_key=None)
    )()
    assert result.ok is False
    assert result.detail is not None
    assert "groq_api_key" in result.detail
    assert "openrouter_api_key" in result.detail


async def test_llm_check_ready_when_configured() -> None:
    result = await make_llm_check(
        Settings(llm_mode="live", groq_api_key="g", openrouter_api_key="o")
    )()
    assert result.ok is True
    assert result.detail is None


async def test_readiness_endpoint_reports_llm_not_ready_when_unconfigured() -> None:
    app = create_app(Settings(app_env="development", log_json=False, llm_mode="live"))
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client,
    ):
        ready = await client.get("/health/ready")
        live = await client.get("/health/live")

    assert ready.status_code == 503
    body = ready.json()
    llm = next(check for check in body["checks"] if check["name"] == "llm")
    assert llm["ok"] is False
    assert live.status_code == 200
