from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.intelligence.library import (
    InformationLibraryService,
)
from ai_signal_api.schemas import (
    SavedViewCreate,
    SavedViewPatch,
    SavedViewRead,
    WorkspaceItemStatePatch,
    WorkspaceItemStateRead,
)


router = APIRouter(prefix="/api", tags=["information"])


@router.patch(
    "/information/{item_id}/state",
    response_model=WorkspaceItemStateRead,
)
def update_information_state(
    item_id: str,
    payload: WorkspaceItemStatePatch,
    session: Session = Depends(get_session),
) -> WorkspaceItemStateRead:
    try:
        return InformationLibraryService(session).update_state(
            item_id,
            payload,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/saved-views", response_model=list[SavedViewRead])
def list_saved_views(
    session: Session = Depends(get_session),
) -> list[SavedViewRead]:
    return [
        SavedViewRead.model_validate(view)
        for view in InformationLibraryService(session).list_views()
    ]


@router.post(
    "/saved-views",
    response_model=SavedViewRead,
    status_code=status.HTTP_201_CREATED,
)
def create_saved_view(
    payload: SavedViewCreate,
    session: Session = Depends(get_session),
) -> SavedViewRead:
    try:
        view = InformationLibraryService(session).create_view(payload)
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="SAVED_VIEW_NAME_EXISTS",
        ) from error
    return SavedViewRead.model_validate(view)


@router.patch(
    "/saved-views/{view_id}",
    response_model=SavedViewRead,
)
def patch_saved_view(
    view_id: str,
    payload: SavedViewPatch,
    session: Session = Depends(get_session),
) -> SavedViewRead:
    try:
        view = InformationLibraryService(session).patch_view(
            view_id,
            payload,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="SAVED_VIEW_NAME_EXISTS",
        ) from error
    return SavedViewRead.model_validate(view)


@router.delete(
    "/saved-views/{view_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_saved_view(
    view_id: str,
    session: Session = Depends(get_session),
) -> None:
    try:
        InformationLibraryService(session).delete_view(view_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
