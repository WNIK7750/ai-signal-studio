from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.modules.intelligence.llm_analyzer import build_analyzer
from ai_signal_api.modules.tasking.service import TaskingService
from ai_signal_api.schemas import (
    TaskCreate,
    TaskPatch,
    TaskPreviewInput,
    TaskPreviewResult,
    TaskRead,
    TaskRunRead,
    TaskRunRetry,
    TaskRunStart,
)


router = APIRouter(prefix="/api", tags=["tasks"])


def _service(request: Request, session: Session) -> TaskingService:
    settings = request.app.state.settings
    return TaskingService(
        session,
        CollectionService(
            session,
            analyzer=build_analyzer(settings),
        ),
    )


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(
    request: Request,
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    return _service(request, session).list_tasks()


@router.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_task(
    payload: TaskCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRead:
    try:
        task = _service(request, session).create_task(payload)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="TASK_NAME_EXISTS",
        ) from error
    if request.app.state.scheduler is not None:
        request.app.state.sync_collection_task(task.id)
    return task


@router.get("/tasks/{task_id}", response_model=TaskRead)
def get_task(
    task_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRead:
    try:
        return _service(request, session).get_task(task_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def patch_task(
    task_id: str,
    payload: TaskPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRead:
    try:
        task = _service(request, session).patch_task(task_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="TASK_NAME_EXISTS",
        ) from error
    if request.app.state.scheduler is not None:
        request.app.state.sync_collection_task(task.id)
    return task


@router.post(
    "/tasks/{task_id}/preview",
    response_model=TaskPreviewResult,
)
def preview_task(
    task_id: str,
    payload: TaskPreviewInput,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskPreviewResult:
    try:
        return _service(request, session).preview(task_id, payload.config)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/tasks/{task_id}/runs",
    response_model=TaskRunRead,
    status_code=status.HTTP_201_CREATED,
)
def start_task_run(
    task_id: str,
    payload: TaskRunStart,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRunRead:
    try:
        return _service(request, session).run(
            task_id,
            task_version_id=payload.task_version_id,
            trigger_type=payload.trigger_type,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/task-runs/{run_id}", response_model=TaskRunRead)
def get_task_run(
    run_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRunRead:
    try:
        return _service(request, session).get_run(run_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/task-runs/{run_id}/retry",
    response_model=TaskRunRead,
    status_code=status.HTTP_201_CREATED,
)
def retry_task_run(
    run_id: str,
    payload: TaskRunRetry,
    request: Request,
    session: Session = Depends(get_session),
) -> TaskRunRead:
    try:
        return _service(request, session).retry_run(
            run_id,
            mode=payload.mode,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
