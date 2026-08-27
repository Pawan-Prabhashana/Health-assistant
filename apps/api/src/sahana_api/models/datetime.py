"""Timezone-aware datetime column helper.

Every datetime column in the schema is ``timestamptz`` and handled in UTC. This
helper is the single way to declare one, so a naive ``timestamp`` column can
never slip into the model.
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utc_timestamptz(*, nullable: bool, **kwargs: Any) -> Mapped[datetime.datetime]:
    """Return a ``timestamptz`` column. Values are always timezone-aware UTC."""
    return mapped_column(DateTime(timezone=True), nullable=nullable, **kwargs)
