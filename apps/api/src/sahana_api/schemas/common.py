"""Shared schema types: the error envelope and pagination bounds."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Pagination bounds applied to every list endpoint so a query can never dump an
# unbounded result set.
DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class FieldError(BaseModel):
    """A single field-level validation problem. Carries no submitted values."""

    field: str = Field(description="Dotted path to the offending field.")
    message: str = Field(description="Human-readable reason, free of submitted data.")


class ErrorDetail(BaseModel):
    """The body of an error, identifying the class of failure."""

    code: str = Field(description="Stable, machine-readable error code.")
    message: str = Field(description="Human-readable summary, free of personal data.")
    fields: list[FieldError] = Field(
        default_factory=list,
        description="Field-level details for validation errors; empty otherwise.",
    )


class ErrorEnvelope(BaseModel):
    """The consistent error response shape returned by every endpoint."""

    error: ErrorDetail
