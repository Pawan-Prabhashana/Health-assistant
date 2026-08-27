"""Request-scoped database session dependency."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.db.engine import Database, DatabaseNotConfiguredError


def get_database(request: Request) -> Database:
    """Return the :class:`Database` attached to application state.

    :raises DatabaseNotConfiguredError: if the app booted without a configured
        database. Routes that require persistence surface this as a 503 via the
        registered exception handler.
    """
    database: Database | None = request.app.state.db
    if database is None:
        raise DatabaseNotConfiguredError("database is not configured")
    return database


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a session per request, committing on success and rolling back on error.

    The session is closed in all cases. Handlers never manage transactions
    directly; they simply use the yielded session and let this dependency own
    commit/rollback semantics.
    """
    database = get_database(request)
    async with database.sessionmaker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
