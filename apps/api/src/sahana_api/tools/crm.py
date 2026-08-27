"""CRM tool path: identity-gated, own-data-only, deterministically rendered.

A CRM answer requires an identified patient (resolved upstream and carried in
``context.patient_id``); an unidentified caller gets the identify-first response
and no data. The tool only ever queries by the caller's own id, so it is
structurally impossible to return another patient's records. All figures are
rendered deterministically from the repository rows — the LLM never sees or alters
them (see ADR 0011).
"""

from __future__ import annotations

import datetime
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.graph.schemas import Route
from sahana_api.graph.state import StructuredTable
from sahana_api.graph.tools import ToolRequest, ToolResult
from sahana_api.logging import get_logger
from sahana_api.models.appointment import Appointment
from sahana_api.repositories.appointments import AppointmentRepository
from sahana_api.repositories.patients import PatientRepository
from sahana_api.tools.prompts import CRM_SAFETY_FOOTER, IDENTIFY_REQUIRED, RECORDS_UNAVAILABLE

_logger = get_logger("sahana_api.tools.crm")

SessionProvider = Callable[[], AbstractAsyncContextManager[AsyncSession]]

_COLUMNS = ["Patient ID", "Name", "Status", "Next Appt"]


def _render_next_appt(appointment: Appointment | None) -> str:
    if appointment is None:
        return "None scheduled"
    when = appointment.scheduled_for.strftime("%Y-%m-%d %H:%M UTC")
    return f"{appointment.department} on {when}"


def _render_plain(table: StructuredTable) -> str:
    """Deterministic plain-text rendering of the single-patient CRM row."""
    row = table.rows[0]
    lines = [f"{column}: {value}" for column, value in zip(table.columns, row, strict=True)]
    return "Here are your records:\n" + "\n".join(lines) + "\n\n" + CRM_SAFETY_FOOTER


def _identify_result() -> ToolResult:
    return ToolResult(
        route=Route.CRM, payload=IDENTIFY_REQUIRED, metadata={"status": "identify_required"}
    )


class CrmTool:
    """Builds the CRM table reply for the identified caller only."""

    route = Route.CRM

    def __init__(self, session_provider: SessionProvider | None) -> None:
        self._session_provider = session_provider

    async def run(self, request: ToolRequest) -> ToolResult:
        patient_id = request.context.patient_id
        if patient_id is None:
            return _identify_result()
        if self._session_provider is None:
            _logger.warning("crm.unavailable", reason="database_not_configured")
            return ToolResult(
                route=Route.CRM,
                payload=RECORDS_UNAVAILABLE,
                metadata={"status": "unavailable"},
            )

        async with self._session_provider() as session:
            patient = await PatientRepository(session).get_by_id(patient_id)
            if patient is None:
                return _identify_result()
            appointment = await AppointmentRepository(session).next_upcoming_for_patient(
                patient_id, now=datetime.datetime.now(datetime.UTC)
            )

        table = StructuredTable(
            columns=list(_COLUMNS),
            rows=[
                [
                    patient.mrn,
                    patient.full_name,
                    patient.status.value,
                    _render_next_appt(appointment),
                ]
            ],
        )
        _logger.info("crm.lookup", identified=True, status=patient.status.value)
        return ToolResult(
            route=Route.CRM,
            payload=_render_plain(table),
            structured=table,
            metadata={"status": "crm_ok"},
        )
