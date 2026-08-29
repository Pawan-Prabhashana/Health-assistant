"""Leaf state types shared by the state schema and the tool layer.

These live in their own module so both ``graph.state`` (which references
``ToolResult``) and ``graph.tools`` (which references ``RequestContext`` and
``StructuredTable``) can import them without a cycle.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StructuredTable:
    """A column/row table an authoritative tool renders (e.g. the CRM reply)."""

    columns: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class RequestContext:
    """Caller context for a chat turn.

    ``phone`` is the caller's number (resolved to ``patient_id`` by the graph's
    ``patient_lookup_node``); ``patient_id`` may also be passed pre-resolved.
    """

    session_id: uuid.UUID | None = None
    patient_id: uuid.UUID | None = None
    phone: str | None = None


@dataclass(frozen=True)
class TraceEntry:
    """One node's structured contribution to the reasoning trace (PII-free)."""

    node: str
    data: dict[str, Any] = field(default_factory=dict)
