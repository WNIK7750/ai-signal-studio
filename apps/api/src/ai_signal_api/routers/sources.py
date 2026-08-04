from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.collection.service import SourceService
from ai_signal_api.schemas import (
    SourceCreate,
    SourcePatch,
    SourceRead,
)


router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=list[SourceRead])
def list_sources(session: Session = Depends(get_session)) -> list[SourceRead]:
    return [
        SourceRead.model_validate(source)
        for source in SourceService(session).list()
    ]


@router.post(
    "",
    response_model=SourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    payload: SourceCreate,
    session: Session = Depends(get_session),
) -> SourceRead:
    try:
        source = SourceService(session).create(**payload.model_dump())
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="SOURCE_NAME_EXISTS",
        ) from error
    return SourceRead.model_validate(source)


@router.patch("/{source_id}", response_model=SourceRead)
def patch_source(
    source_id: str,
    payload: SourcePatch,
    session: Session = Depends(get_session),
) -> SourceRead:
    try:
        source = SourceService(session).patch(
            source_id,
            payload.model_dump(exclude_unset=True),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return SourceRead.model_validate(source)

