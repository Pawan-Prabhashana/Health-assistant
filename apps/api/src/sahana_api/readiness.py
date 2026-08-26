"""Readiness check registry.

The registry is the extension point for readiness probing. Later phases register
dependency checks (Postgres, Qdrant, LLM providers) by appending to a registry
instance; the endpoint handler never changes. Each check is an async callable
returning a :class:`Check`, and all registered checks run concurrently so a
readiness probe costs one round-trip rather than the sum of its parts.

In Phase 0 no checks are registered: the system has no external dependencies to
verify yet, so readiness is trivially ``true`` with an empty check list.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sahana_api.schemas.health import Check, ReadinessResponse

DependencyCheck = Callable[[], Awaitable[Check]]


class ReadinessRegistry:
    """An ordered collection of dependency checks evaluated concurrently."""

    def __init__(self) -> None:
        self._checks: list[DependencyCheck] = []

    def register(self, check: DependencyCheck) -> None:
        """Add a dependency check to the registry."""
        self._checks.append(check)

    def clear(self) -> None:
        """Remove all registered checks. Primarily used to isolate tests."""
        self._checks.clear()

    async def evaluate(self) -> ReadinessResponse:
        """Run every registered check concurrently and aggregate the result.

        Readiness is the logical AND of all check outcomes. With no checks
        registered the result is ready with an empty list.
        """
        if not self._checks:
            return ReadinessResponse(ready=True, checks=[])

        checks = await asyncio.gather(*(check() for check in self._checks))
        ordered = list(checks)
        return ReadinessResponse(ready=all(c.ok for c in ordered), checks=ordered)
