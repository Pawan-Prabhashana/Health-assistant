"""API routers."""

from __future__ import annotations

from sahana_api.routers.health import router as health_router
from sahana_api.routers.patients import router as patients_router
from sahana_api.routers.sessions import router as sessions_router

__all__ = ["health_router", "patients_router", "sessions_router"]
