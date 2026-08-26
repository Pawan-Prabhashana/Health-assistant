"""Response models for the health and config endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    """Result of a liveness probe. Always cheap and dependency-free."""

    status: Literal["alive"] = "alive"


class Check(BaseModel):
    """The outcome of a single readiness dependency check."""

    name: str = Field(description="Stable identifier for the dependency, e.g. 'postgres'.")
    ok: bool = Field(description="Whether the dependency is currently healthy.")
    detail: str | None = Field(
        default=None,
        description="Optional human-readable context, typically set when 'ok' is false.",
    )


class ReadinessResponse(BaseModel):
    """Aggregate readiness state and the individual dependency checks."""

    ready: bool = Field(description="True only when every check reports ok.")
    checks: list[Check] = Field(
        default_factory=list,
        description="One entry per registered dependency check; empty in Phase 0.",
    )


class ConfigResponse(BaseModel):
    """Non-secret runtime configuration exposed for diagnostics and the UI.

    This model intentionally contains no secrets, connection strings, or API
    keys. Only values safe to display to any client belong here.
    """

    app_name: str
    app_env: str
    version: str
    log_level: str
    features: dict[str, bool] = Field(
        default_factory=dict,
        description="Feature-flag map describing which capabilities are enabled.",
    )
