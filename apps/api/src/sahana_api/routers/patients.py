"""Patient endpoints: phone-based identity and PDPA erasure."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.db.session import get_session
from sahana_api.errors import NotFoundError
from sahana_api.phone import NormalizedPhone
from sahana_api.repositories.patients import PatientRepository
from sahana_api.schemas.common import ErrorEnvelope
from sahana_api.schemas.patients import PatientCreate, PatientResponse

router = APIRouter(prefix="/patients", tags=["patients"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


@router.post(
    "",
    response_model=PatientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update a patient by phone",
)
async def upsert_patient(
    payload: PatientCreate, session: SessionDep, response: Response
) -> PatientResponse:
    """Upsert by phone: ``201`` when created, ``200`` when an existing row is updated."""
    repository = PatientRepository(session)
    patient, created = await repository.upsert_by_phone(payload.phone, payload.full_name)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return PatientResponse.model_validate(patient)


@router.get(
    "/{patient_id}",
    response_model=PatientResponse,
    responses=_NOT_FOUND,
    summary="Fetch a patient by id",
)
async def get_patient(patient_id: uuid.UUID, session: SessionDep) -> PatientResponse:
    """Return a patient by UUID, or ``404`` if absent."""
    patient = await PatientRepository(session).get_by_id(patient_id)
    if patient is None:
        raise NotFoundError("patient")
    return PatientResponse.model_validate(patient)


@router.get(
    "/by-phone/{phone}",
    response_model=PatientResponse,
    responses=_NOT_FOUND,
    summary="Resolve a patient by phone",
)
async def get_patient_by_phone(phone: NormalizedPhone, session: SessionDep) -> PatientResponse:
    """Resolve identity by phone (E.164-normalized), or ``404`` if absent."""
    patient = await PatientRepository(session).get_by_phone(phone)
    if patient is None:
        raise NotFoundError("patient")
    return PatientResponse.model_validate(patient)


@router.delete(
    "/{patient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="Erase a patient (PDPA right to erasure)",
)
async def delete_patient(patient_id: uuid.UUID, session: SessionDep) -> Response:
    """Hard-delete a patient and cascade appointments, sessions, and messages."""
    deleted = await PatientRepository(session).delete_by_id(patient_id)
    if not deleted:
        raise NotFoundError("patient")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
