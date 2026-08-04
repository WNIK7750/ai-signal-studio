from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.automation.service import AutomationService
from ai_signal_api.schemas import (
    CommonPlanCreate,
    CommonPlanPatch,
    CommonPlanRead,
    ScheduledTaskCreate,
    ScheduledTaskPatch,
    ScheduledTaskRead,
)


router = APIRouter(prefix="/api", tags=["automation"])


def _service(request: Request, session: Session) -> AutomationService:
    return AutomationService(session, request.app.state.settings.timezone)


@router.get("/plans", response_model=list[CommonPlanRead])
def list_plans(
    request: Request,
    session: Session = Depends(get_session),
) -> list[CommonPlanRead]:
    return [
        CommonPlanRead.model_validate(plan)
        for plan in _service(request, session).list_plans()
    ]


@router.post(
    "/plans",
    response_model=CommonPlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(
    payload: CommonPlanCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> CommonPlanRead:
    plan = _service(request, session).create_plan(payload.model_dump())
    return CommonPlanRead.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=CommonPlanRead)
def patch_plan(
    plan_id: str,
    payload: CommonPlanPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> CommonPlanRead:
    try:
        plan = _service(request, session).patch_plan(
            plan_id,
            payload.model_dump(exclude_unset=True),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return CommonPlanRead.model_validate(plan)


@router.get("/scheduled-tasks", response_model=list[ScheduledTaskRead])
def list_scheduled_tasks(
    request: Request,
    session: Session = Depends(get_session),
) -> list[ScheduledTaskRead]:
    return [
        ScheduledTaskRead.model_validate(task)
        for task in _service(request, session).list_tasks()
    ]


@router.post(
    "/scheduled-tasks",
    response_model=ScheduledTaskRead,
    status_code=status.HTTP_201_CREATED,
)
def create_scheduled_task(
    payload: ScheduledTaskCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> ScheduledTaskRead:
    try:
        task = _service(request, session).create_task(payload.model_dump())
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="SCHEDULE_NAME_EXISTS",
        ) from error
    if request.app.state.scheduler is not None:
        request.app.state.sync_scheduled_task(task.id)
    return ScheduledTaskRead.model_validate(task)


@router.patch(
    "/scheduled-tasks/{task_id}",
    response_model=ScheduledTaskRead,
)
def patch_scheduled_task(
    task_id: str,
    payload: ScheduledTaskPatch,
    request: Request,
    session: Session = Depends(get_session),
) -> ScheduledTaskRead:
    try:
        task = _service(request, session).patch_task(
            task_id,
            payload.model_dump(exclude_unset=True),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if request.app.state.scheduler is not None:
        request.app.state.sync_scheduled_task(task.id)
    return ScheduledTaskRead.model_validate(task)
