"""Prometheus metrics for the Sahana API.

Exposes the numbers that let an operator reason about the latency budgets and the
router spend, especially on refused queries: per-turn count and latency labelled
by route and verdict, the verdict/route distribution, the CAG cache hit rate,
LLM token and estimated-cost counters labelled by role and model, and error
counts. ``/metrics`` is an operational endpoint (Prometheus text exposition), not
one of the sixteen business endpoints. Metric values carry no PII — only bounded
label sets (routes, verdicts, roles, model ids, error codes).
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# Latency buckets tuned to the documented budgets: ~0.29s cached, ~1.7s refusals,
# 2-2.5s tool-backed answers, with headroom on either side.
_LATENCY_BUCKETS = (0.05, 0.1, 0.29, 0.5, 1.0, 1.7, 2.5, 4.0, 8.0)

chat_turns_total = Counter(
    "sahana_chat_turns_total",
    "Chat turns completed, by pipeline route and verdict.",
    ("route", "verdict"),
)
chat_turn_latency_seconds = Histogram(
    "sahana_chat_turn_latency_seconds",
    "End-to-end chat turn latency, by route and verdict.",
    ("route", "verdict"),
    buckets=_LATENCY_BUCKETS,
)
chat_cache_total = Counter(
    "sahana_chat_cache_total",
    "Chat turns by CAG cache outcome (hit or miss).",
    ("result",),
)
chat_errors_total = Counter(
    "sahana_chat_errors_total",
    "Chat pipeline errors, by error code.",
    ("code",),
)
llm_tokens_total = Counter(
    "sahana_llm_tokens_total",
    "LLM tokens consumed, by role, model, and kind (prompt or completion).",
    ("role", "model", "kind"),
)
llm_cost_usd_total = Counter(
    "sahana_llm_cost_usd_total",
    "Estimated LLM cost in USD, by role and model.",
    ("role", "model"),
)

_NONE_ROUTE = "none"


def record_turn(route: str | None, verdict: str, latency_ms: float) -> None:
    """Record one completed chat turn's route, verdict, and latency."""
    route_label = route if route is not None else _NONE_ROUTE
    chat_turns_total.labels(route=route_label, verdict=verdict).inc()
    chat_turn_latency_seconds.labels(route=route_label, verdict=verdict).observe(
        latency_ms / 1000.0
    )
    chat_cache_total.labels(result="hit" if verdict == "cache_hit" else "miss").inc()


def record_error(code: str) -> None:
    """Record one chat pipeline error by code."""
    chat_errors_total.labels(code=code).inc()


def record_llm_usage(
    role: str, model: str, prompt_tokens: int, completion_tokens: int, cost_usd: float
) -> None:
    """Record token and estimated-cost counters for one LLM call."""
    llm_tokens_total.labels(role=role, model=model, kind="prompt").inc(prompt_tokens)
    llm_tokens_total.labels(role=role, model=model, kind="completion").inc(completion_tokens)
    llm_cost_usd_total.labels(role=role, model=model).inc(cost_usd)


router = APIRouter(tags=["ops"])


@router.get("/metrics", summary="Prometheus metrics (operational, not a business endpoint)")
async def metrics() -> Response:
    """Return the current metrics in Prometheus text exposition format."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
