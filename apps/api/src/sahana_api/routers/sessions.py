"""Session endpoints: conversation-thread CRUD."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sahana_api.db.session import get_session
from sahana_api.errors import NotFoundError
from sahana_api.models.session import Session
from sahana_api.phone import NormalizedPhone
from sahana_api.repositories.patients import PatientRepository
from sahana_api.repositories.sessions import SessionRepository
from sahana_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT, ErrorEnvelope
from sahana_api.schemas.sessions import (
    MessageResponse,
    SessionCreate,
    SessionDetailResponse,
    SessionResponse,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_NOT_FOUND: dict[int | str, dict[str, Any]] = {status.HTTP_404_NOT_FOUND: {"model": ErrorEnvelope}}


async def _resolve_patient_id(session: AsyncSession, phone: str) -> uuid.UUID | None:
    """Resolve a normalized phone to a patient id, or ``None`` if unknown."""
    patient = await PatientRepository(session).get_by_phone(phone)
    return patient.id if patient is not None else None


@router.post(
    "",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a conversation thread",
)
async def create_session(payload: SessionCreate, session: SessionDep) -> SessionResponse:
    """Create a thread, associating a patient when the phone resolves."""
    patient_id = (
        await _resolve_patient_id(session, payload.phone) if payload.phone is not None else None
    )
    thread = await SessionRepository(session).create(patient_id=patient_id, title=payload.title)
    return SessionResponse.model_validate(thread)


@router.get(
    "",
    response_model=list[SessionResponse],
    summary="List conversation threads for a patient",
)
async def list_sessions(
    session: SessionDep,
    phone: Annotated[NormalizedPhone | None, Query(description="Caller phone filter.")] = None,
    patient_id: Annotated[uuid.UUID | None, Query(description="Patient id filter.")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[SessionResponse]:
    """List a patient's threads, newest first. A ``phone`` or ``patient_id`` is required."""
    resolved_id = patient_id
    if resolved_id is None and phone is not None:
        resolved_id = await _resolve_patient_id(session, phone)
        if resolved_id is None:
            return []
    if resolved_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a phone or patient_id filter is required",
        )
    threads = await SessionRepository(session).list_for_patient(
        resolved_id, limit=limit, offset=offset
    )
    return [SessionResponse.model_validate(thread) for thread in threads]


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponse,
    responses=_NOT_FOUND,
    summary="Fetch a conversation thread",
)
async def get_session_by_id(
    session_id: uuid.UUID,
    session: SessionDep,
    include: Annotated[Literal["messages"] | None, Query()] = None,
) -> SessionDetailResponse:
    """Fetch a thread; ``?include=messages`` embeds its messages."""
    repository = SessionRepository(session)
    thread: Session | None
    if include == "messages":
        thread = await repository.get_with_messages(session_id)
    else:
        thread = await repository.get_by_id(session_id)
    if thread is None:
        raise NotFoundError("session")

    messages = (
        [MessageResponse.model_validate(message) for message in thread.messages]
        if include == "messages"
        else None
    )
    return SessionDetailResponse(
        id=thread.id,
        patient_id=thread.patient_id,
        title=thread.title,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=messages,
    )


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="Delete a conversation thread",
)
async def delete_session(session_id: uuid.UUID, session: SessionDep) -> Response:
    """Delete a thread and cascade its messages."""
    deleted = await SessionRepository(session).delete_by_id(session_id)
    if not deleted:
        raise NotFoundError("session")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
