"""LLM provider readiness check.

The check verifies that the roles Sahana needs have a key and a model configured;
it does not make a live inference call, so readiness never burns tokens or adds
latency. Fake mode is always ready. When configuration is missing, the detail
lists exactly which pieces are absent (names only, never values).
"""

from __future__ import annotations

from sahana_api.config import Settings
from sahana_api.readiness import DependencyCheck
from sahana_api.schemas.health import Check


def make_llm_check(settings: Settings) -> DependencyCheck:
    """Return a config-only readiness check for the LLM provider layer."""

    async def check() -> Check:
        if settings.llm_mode == "fake":
            return Check(name="llm", ok=True, detail="fake mode")

        missing: list[str] = []
        if settings.groq_api_key is None:
            missing.append("groq_api_key")
        if not settings.guardrail_model:
            missing.append("guardrail_model")
        if not settings.router_model:
            missing.append("router_model")
        if settings.openrouter_api_key is None:
            missing.append("openrouter_api_key")
        if not settings.synth_model:
            missing.append("synth_model")

        if missing:
            return Check(name="llm", ok=False, detail="missing config: " + ", ".join(missing))
        return Check(name="llm", ok=True, detail=None)

    return check
