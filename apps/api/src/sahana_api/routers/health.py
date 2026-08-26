"""Health and configuration endpoints.

Three endpoints make up the Phase 0 feature surface:

* ``GET /health/live``  — liveness, always cheap, backs the container probe.
* ``GET /health/ready`` — readiness, aggregates the dependency-check registry.
* ``GET /config``       — non-secret runtime configuration for the UI.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from sahana_api.config import Settings, get_settings
from sahana_api.readiness import ReadinessRegistry
from sahana_api.schemas.health import ConfigResponse, LivenessResponse, ReadinessResponse
from sahana_api.version import __version__

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_readiness_registry(request: Request) -> ReadinessRegistry:
    """Return the readiness registry attached to the application state."""
    registry: ReadinessRegistry = request.app.state.readiness
    return registry


ReadinessDep = Annotated[ReadinessRegistry, Depends(get_readiness_registry)]

# Capabilities exposed via /config. Every route is inert in Phase 0; later phases
# flip these to true as each capability is wired in.
_PHASE0_FEATURES: dict[str, bool] = {
    "crm_lookup": False,
    "rag": False,
    "concierge": False,
    "web_search": False,
    "cag_cache": False,
}


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    tags=["health"],
)
async def liveness() -> LivenessResponse:
    """Report that the process is running. Performs no dependency work."""
    return LivenessResponse()


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    tags=["health"],
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadinessResponse}},
)
async def readiness(registry: ReadinessDep, response: Response) -> ReadinessResponse:
    """Aggregate the readiness-check registry and set the HTTP status.

    Returns ``503`` when any dependency check fails so orchestrators treat the
    instance as not-ready without parsing the body.
    """
    result = await registry.evaluate()
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get(
    "/config",
    response_model=ConfigResponse,
    summary="Non-secret runtime configuration",
    tags=["config"],
)
async def config(settings: SettingsDep) -> ConfigResponse:
    """Return runtime configuration safe to expose to any client.

    Secrets, API keys, and connection strings are never included.
    """
    return ConfigResponse(
        app_name=settings.app_name,
        app_env=settings.app_env,
        version=__version__,
        log_level=settings.log_level,
        features=dict(_PHASE0_FEATURES),
    )
