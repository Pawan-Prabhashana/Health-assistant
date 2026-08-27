"""Unit tests for the pure decision logic (no LLM, no I/O)."""

from __future__ import annotations

from sahana_api.cag.cache import CagCandidate
from sahana_api.graph.decide import RouteMatchPolicy, decide
from sahana_api.graph.schemas import GuardrailVerdict, Route, RouteDecision, Verdict

_CACHEABLE = ["rag", "concierge", "web_search"]


def _guard(in_scope: bool) -> GuardrailVerdict:
    return GuardrailVerdict(in_scope=in_scope, category="x", reason="y")


def _route(route: Route, confidence: float) -> RouteDecision:
    return RouteDecision(
        route=route, confidence=confidence, reason="y", needs_patient_identity=False
    )


def _decide(
    guardrail: GuardrailVerdict | None,
    route: RouteDecision | None,
    cag: CagCandidate | None,
    *,
    policy: RouteMatchPolicy = "any_allowlisted",
) -> object:
    return decide(
        guardrail,
        route,
        cag,
        threshold=0.9,
        cacheable_routes=_CACHEABLE,
        min_confidence=0.5,
        fallback_route=Route.DIRECT,
        route_match_policy=policy,
    )


def test_out_of_scope_wins() -> None:
    outcome = _decide(_guard(False), _route(Route.RAG, 0.9), None)
    assert outcome.verdict is Verdict.OUT_OF_SCOPE
    assert outcome.route is None


def test_missing_guardrail_fails_closed() -> None:
    outcome = _decide(None, _route(Route.RAG, 0.9), None)
    assert outcome.verdict is Verdict.OUT_OF_SCOPE


def test_out_of_scope_beats_cache() -> None:
    candidate = CagCandidate(answer="a", route="rag", score=0.99, expired=False)
    outcome = _decide(_guard(False), _route(Route.RAG, 0.9), candidate)
    assert outcome.verdict is Verdict.OUT_OF_SCOPE


def test_gated_cache_hit() -> None:
    candidate = CagCandidate(answer="a", route="rag", score=0.95, expired=False)
    outcome = _decide(_guard(True), _route(Route.RAG, 0.9), candidate)
    assert outcome.verdict is Verdict.CACHE_HIT
    assert outcome.cache_gated_in is True


def test_cache_below_threshold_proceeds() -> None:
    candidate = CagCandidate(answer="a", route="rag", score=0.5, expired=False)
    outcome = _decide(_guard(True), _route(Route.RAG, 0.9), candidate)
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.RAG


def test_expired_cache_proceeds() -> None:
    candidate = CagCandidate(answer="a", route="rag", score=0.99, expired=True)
    outcome = _decide(_guard(True), _route(Route.RAG, 0.9), candidate)
    assert outcome.verdict is Verdict.PROCEED


def test_non_allowlisted_cache_route_proceeds() -> None:
    # A high-scoring candidate stored under crm is never served.
    candidate = CagCandidate(answer="a", route="crm", score=0.99, expired=False)
    outcome = _decide(_guard(True), _route(Route.DIRECT, 0.9), candidate)
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.DIRECT


def test_match_router_policy_rejects_mismatch() -> None:
    candidate = CagCandidate(answer="a", route="rag", score=0.99, expired=False)
    outcome = _decide(_guard(True), _route(Route.WEB_SEARCH, 0.9), candidate, policy="match_router")
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.WEB_SEARCH


def test_proceed_with_router_route() -> None:
    outcome = _decide(_guard(True), _route(Route.CRM, 0.8), None)
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.CRM


def test_low_confidence_falls_back() -> None:
    outcome = _decide(_guard(True), _route(Route.WEB_SEARCH, 0.2), None)
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.DIRECT
    assert outcome.branch == "proceed_low_confidence"


def test_missing_route_falls_back() -> None:
    outcome = _decide(_guard(True), None, None)
    assert outcome.verdict is Verdict.PROCEED
    assert outcome.route is Route.DIRECT
