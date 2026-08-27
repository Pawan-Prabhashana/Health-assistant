"""Session and message request/response schemas.

Session responses carry no patient PII (only the ``patient_id`` reference), so
they are safe to return from the list endpoint.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sahana_api.models.enums import MessageRole
from sahana_api.phone import InvalidPhoneNumberError, normalize_phone


class SessionCreate(BaseModel):
    """Body for ``POST /sessions``."""

    phone: str | None = Field(
        default=None,
        description="Optional caller phone; if it resolves, the session is associated.",
    )
    title: str | None = Field(
        default=None,
        max_length=200,
        description="Optional thread title; a default is applied when omitted.",
    )

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            return normalize_phone(value)
        except InvalidPhoneNumberError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class MessageResponse(BaseModel):
    """A message embedded in a session detail response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    role: MessageRole
    content: str
    metadata: dict[str, Any] = Field(validation_alias="meta", serialization_alias="metadata")
    created_at: datetime.datetime


class SessionResponse(BaseModel):
    """A conversation thread. Contains no patient PII."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID | None
    title: str
    created_at: datetime.datetime
    updated_at: datetime.datetime


class SessionDetailResponse(SessionResponse):
    """Session with optionally embedded messages (``?include=messages``)."""

    messages: list[MessageResponse] | None = Field(
        default=None,
        description="Present only when messages are requested; otherwise null.",
    )
