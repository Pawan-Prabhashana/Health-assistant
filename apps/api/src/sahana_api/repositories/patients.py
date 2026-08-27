"""Patient repository."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.models.patient import Patient

# Applied when a patient is created without a supplied name (e.g. an anonymous
# caller identified only by phone). Documented in docs/adr/0005.
DEFAULT_PATIENT_NAME = "Unknown"


class PatientRepository:
    """Data access for the patient aggregate."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, patient_id: uuid.UUID) -> Patient | None:
        """Return the patient with ``patient_id`` or ``None``."""
        return await self._session.get(Patient, patient_id)

    async def get_by_phone(self, phone: str) -> Patient | None:
        """Return the patient with the normalized ``phone`` or ``None``."""
        result = await self._session.execute(select(Patient).where(Patient.phone == phone))
        return result.scalar_one_or_none()

    async def upsert_by_phone(self, phone: str, full_name: str | None) -> tuple[Patient, bool]:
        """Create or update a patient keyed by ``phone``.

        Returns the patient and ``True`` when a new row was created, ``False``
        when an existing row was returned (its name updated if one was supplied).
        """
        existing = await self.get_by_phone(phone)
        if existing is not None:
            if full_name is not None and full_name != existing.full_name:
                existing.full_name = full_name
            await self._session.flush()
            return existing, False

        patient = Patient(phone=phone, full_name=full_name or DEFAULT_PATIENT_NAME)
        self._session.add(patient)
        await self._session.flush()
        return patient, True

    async def delete_by_id(self, patient_id: uuid.UUID) -> bool:
        """Hard-delete a patient, cascading appointments, sessions, and messages.

        Returns ``True`` if a row was deleted, ``False`` if none matched.
        """
        patient = await self.get_by_id(patient_id)
        if patient is None:
            return False
        await self._session.delete(patient)
        await self._session.flush()
        return True
