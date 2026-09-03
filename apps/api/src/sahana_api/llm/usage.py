"""Cost estimation and structured usage logging.

Cost is estimated from the config-driven price table (prices drift, so they are
never hardcoded). Every completion emits a structured ``llm.usage`` log carrying
role, model, tokens, estimated cost, and latency — the record Phase 6 writes into
``messages.metadata`` and Phase 9 aggregates into metrics. Message content is
never logged, so no PII reaches the logs.
"""

from __future__ import annotations

from sahana_api.config import ModelPrice
from sahana_api.llm.base import Role, Usage
from sahana_api.logging import get_logger
from sahana_api.metrics import record_llm_usage

_logger = get_logger("sahana_api.llm.usage")

_TOKENS_PER_MILLION = 1_000_000


def estimate_cost(
    prices: dict[str, ModelPrice],
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate USD cost from the price table; unknown models cost 0.0."""
    price = prices.get(model)
    if price is None:
        return 0.0
    input_cost = prompt_tokens / _TOKENS_PER_MILLION * price.input_per_1m
    output_cost = completion_tokens / _TOKENS_PER_MILLION * price.output_per_1m
    return round(input_cost + output_cost, 8)


def log_usage(role: Role, model: str, usage: Usage) -> None:
    """Emit the structured usage log for one completion and update metrics."""
    _logger.info(
        "llm.usage",
        role=role,
        model=model,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        estimated_cost_usd=usage.estimated_cost_usd,
        latency_ms=usage.latency_ms,
    )
    record_llm_usage(
        role, model, usage.prompt_tokens, usage.completion_tokens, usage.estimated_cost_usd
    )
