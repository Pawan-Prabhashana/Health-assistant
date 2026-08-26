"""Sahana hospital health assistant API.

Phase 0 exposes the application foundation: configuration, structured logging,
and the health/config endpoints. Later phases add chat, routing, persistence,
vector search, and LLM providers on top of this skeleton.
"""

from __future__ import annotations

from sahana_api.version import __version__

__all__ = ["__version__"]
