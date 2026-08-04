from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.schemas import (
    CollectionRunRead,
    CollectionRunStart,
    ExecutionContext,
    Priority,
    SourceKind,
    TimelinePage,
    TimelineQuery,
)


router = APIRouter(prefix="/api", tags=["timeline"])


@router.post(
    "/collection-runs",
    response_model=CollectionRunRead,
    status_code=status.HTTP_201_CREATED,
)
def start_collection_run(
    payload: CollectionRunStart,
    request: Request,
    session: Session = Depends(get_session),
) -> CollectionRunRead:
    result = build_capability_executor(
        session,
        request.app.state.settings,
    ).execute(
        "collection.run.start",
        payload,
        ExecutionContext(
            request_id=f"req_{uuid4().hex}",
            actor_type="user",
        ),
    )
    return CollectionRunRead.model_validate(result)


@router.get("/collection-runs", response_model=list[CollectionRunRead])
def list_collection_runs(
    session: Session = Depends(get_session),
) -> list[CollectionRunRead]:
    return [
        CollectionRunRead.model_validate(run)
        for run in CollectionService(session).list_runs()
    ]


@router.get(
    "/collection-runs/{run_id}",
    response_model=CollectionRunRead,
)
def get_collection_run(
    run_id: str,
    session: Session = Depends(get_session),
) -> CollectionRunRead:
    try:
        return CollectionRunRead.model_validate(
            CollectionService(session).get_run(run_id)
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/timeline", response_model=TimelinePage)
def query_timeline(
    request: Request,
    search: str | None = Query(default=None),
    priority: Priority | None = Query(default=None),
    source_kind: SourceKind | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> TimelinePage:
    result = build_capability_executor(
        session,
        request.app.state.settings,
    ).execute(
        "intelligence.timeline.query",
        TimelineQuery(
            search=search,
            priority=priority,
            source_kind=source_kind,
            limit=limit,
            offset=offset,
        ),
        ExecutionContext(
            request_id=f"req_{uuid4().hex}",
            actor_type="user",
        ),
    )
    return TimelinePage.model_validate(result)
