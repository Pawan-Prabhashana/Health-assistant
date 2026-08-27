"""Pure decision logic for the fan-in node.

``decide`` reads the three classifier results and emits exactly one verdict,
deterministically, with a fixed precedence (see ADR 0010):

1. Out-of-scope wins first — an out-of-scope question never serves a cached
   answer or fires a tool. Missing guardrail fails closed (out-of-scope).
2. Then a gated cache hit — a candidate at/above threshold, unexpired, whose
   stored route is allowlisted (and satisfies the route-match policy).
3. Otherwise proceed on the router's route, falling back to a safe default when
   the router is missing or below the confidence floor.

This function performs no I/O and makes no LLM call: it is pure, total, and
unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sahana_api.cag.cache import CagCandidate
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision, Verdict

RouteMatchPolicy = Literal["any_allowlisted", "match_router"]


@dataclass(frozen=True)
class DecideOutcome:
    """The verdict plus the precedence branch taken, for the trace."""

    verdict: Verdict
    route: Route | None
    branch: str
    cache_gated_in: bool
    detail: str


def _cache_gated_in(
    cag: CagCandidate,
    route: RouteDecision | None,
    *,
    threshold: float,
    cacheable_routes: list[str],
    policy: RouteMatchPolicy,
) -> tuple[bool, str]:
    """Return whether a cache candidate may be served, and why/why not."""
    if cag.score < threshold:
        return False, "below_threshold"
    if cag.expired:
        return False, "expired"
    if cag.route not in cacheable_routes:
        return False, "route_not_allowlisted"
    if policy == "match_router" and (route is None or cag.route != route.route.value):
        return False, "route_mismatch"
    return True, "gated_in"


def decide(
    guardrail: GuardrailVerdict | None,
    route: RouteDecision | None,
    cag: CagCandidate | None,
    *,
    threshold: float,
    cacheable_routes: list[str],
    min_confidence: float,
    fallback_route: Route,
    route_match_policy: RouteMatchPolicy,
) -> DecideOutcome:
    """Emit the single routing verdict from the three classifier results."""
    # 1. Out-of-scope wins first (fail closed when the guardrail is absent).
    if guardrail is None or not guardrail.in_scope:
        return DecideOutcome(
            Verdict.OUT_OF_SCOPE, None, "out_of_scope", False, "guardrail_out_of_scope"
        )

    # 2. Then a gated cache hit.
    if cag is not None:
        gated_in, why = _cache_gated_in(
            cag,
            route,
            threshold=threshold,
            cacheable_routes=cacheable_routes,
            policy=route_match_policy,
        )
        if gated_in:
            return DecideOutcome(Verdict.CACHE_HIT, None, "cache_hit", True, why)

    # 3. Otherwise proceed, falling back on a missing or low-confidence route.
    if route is None:
        return DecideOutcome(
            Verdict.PROCEED, fallback_route, "proceed_no_route", False, "router_missing"
        )
    if route.confidence < min_confidence:
        return DecideOutcome(
            Verdict.PROCEED, fallback_route, "proceed_low_confidence", False, "below_min_confidence"
        )
    return DecideOutcome(Verdict.PROCEED, route.route, "proceed", False, "router_route")
