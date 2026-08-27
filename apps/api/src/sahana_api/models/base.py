"""Declarative base and shared column helpers.

A single :class:`Base` carries a naming convention so every constraint and index
has a deterministic, readable name (important for reviewable migrations). Shared
timestamp columns are provided as mixins to keep table definitions terse and
consistent. All datetime columns are ``timestamptz`` and handled in UTC.
"""

from __future__ import annotations

import datetime
import enum
import uuid

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic naming so Alembic migrations and the models agree on identifiers.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    """Return a UUID primary-key column generated application-side."""
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def pg_enum[E: enum.Enum](enum_cls: type[E], name: str) -> Enum:
    """Build a native Postgres enum type whose labels are the member values.

    Using ``values_callable`` persists the ``StrEnum`` *values* (e.g. ``stable``)
    rather than the member names, keeping the database labels identical to what
    the API accepts and returns.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=True,
        values_callable=lambda enum_type: [member.value for member in enum_type],
    )


# ``clock_timestamp()`` (wall-clock at row write) is used instead of ``now()``
# (which is fixed to the transaction start) so rows written in the same
# transaction receive strictly increasing timestamps and "newest first" ordering
# is deterministic.
_WRITE_TIME = func.clock_timestamp()


class TimestampMixin:
    """Adds ``created_at``/``updated_at`` timestamptz columns maintained in UTC."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_WRITE_TIME
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=_WRITE_TIME,
        onupdate=_WRITE_TIME,
    )


class CreatedAtMixin:
    """Adds a single ``created_at`` timestamptz column maintained in UTC."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=_WRITE_TIME
    )
