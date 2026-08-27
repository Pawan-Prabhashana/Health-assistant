"""Async database engine and session factory.

The engine is created once per process from :class:`Settings` and disposed on
shutdown (wired in the application lifespan). Because the application connects
through the Supabase transaction pooler (pgbouncer), which is incompatible with
server-side prepared statements, the asyncpg driver is configured with
``statement_cache_size=0``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sahana_api.config import Settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when database access is attempted without a configured URL."""


@dataclass(slots=True)
class Database:
    """Owns the async engine and session factory for the process."""

    engine: AsyncEngine
    sessionmaker: async_sessionmaker[AsyncSession]

    @classmethod
    def from_settings(cls, settings: Settings) -> Database:
        """Build a :class:`Database` from settings.

        :raises DatabaseNotConfiguredError: if ``database_url`` is unset.
        """
        if settings.database_url is None:
            raise DatabaseNotConfiguredError("SAHANA_DATABASE_URL is not configured")

        engine = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            # asyncpg + pgbouncer (transaction mode) cannot use server-side
            # prepared statements; disable the statement cache.
            connect_args={"statement_cache_size": 0},
        )
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
        return cls(engine=engine, sessionmaker=sessionmaker)

    async def dispose(self) -> None:
        """Dispose the engine and its connection pool."""
        await self.engine.dispose()
