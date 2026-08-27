"""Patient request/response schemas.

The single-record patient response includes the patient's own identity fields
(``phone``, ``full_name``); these must never appear in list or aggregate
responses (there are none for patients in this phase).
"""

from __future__ import annotations

import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sahana_api.models.enums import PatientStatus
from sahana_api.phone import InvalidPhoneNumberError, normalize_phone


class PatientCreate(BaseModel):
    """Body for ``POST /patients`` (upsert by phone)."""

    phone: str = Field(description="Phone number in any format; normalized to E.164.")
    full_name: str | None = Field(
        default=None,
        max_length=200,
        description="Optional display name; updated on an existing patient.",
    )

    @field_validator("phone")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except InvalidPhoneNumberError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class PatientResponse(BaseModel):
    """Single-record patient response, including own-identity fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mrn: str
    phone: str
    full_name: str
    status: PatientStatus
    created_at: datetime.datetime
