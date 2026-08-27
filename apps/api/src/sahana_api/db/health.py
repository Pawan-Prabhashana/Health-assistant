"""Postgres readiness check."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from sahana_api.db.engine import Database
from sahana_api.logging import get_logger
from sahana_api.readiness import DependencyCheck
from sahana_api.schemas.health import Check

_logger = get_logger("sahana_api.db.health")


def make_postgres_check(database: Database, *, timeout: float = 2.0) -> DependencyCheck:
    """Return a readiness check that runs a cheap ``SELECT 1`` with a timeout.

    The detail is intentionally generic so no connection string or driver error
    (which may contain host/credential fragments) reaches the response or logs.
    """

    async def check() -> Check:
        try:
            await asyncio.wait_for(_ping(database), timeout=timeout)
        except Exception as exc:  # any failure (timeout, connection) means not-ready
            _logger.warning("readiness.postgres.unreachable", error=type(exc).__name__)
            return Check(name="postgres", ok=False, detail="database unreachable")
        return Check(name="postgres", ok=True, detail=None)

    return check


async def _ping(database: Database) -> None:
    """Open a session and execute ``SELECT 1``."""
    async with database.sessionmaker() as session:
        await session.execute(text("SELECT 1"))
