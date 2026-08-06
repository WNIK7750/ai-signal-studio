from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.cards.service import CardService
from ai_signal_api.modules.cards.poster_graph import PosterGraphRunner
from ai_signal_api.schemas import (
    CardGenerateInput,
    CardGenerateResult,
    CardPage,
    CardRead,
    CardRenderResult,
    CardUpdateInput,
    ExecutionContext,
    Priority,
    SourceKind,
)


router = APIRouter(prefix="/api/cards", tags=["cards"])


class PosterWorkflowStart(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=400, ge=100, le=1000)


class PosterWorkflowResume(BaseModel):
    approved: bool


def _poster_runner(request: Request, session: Session) -> PosterGraphRunner:
    settings = request.app.state.settings
    return PosterGraphRunner(
        CardService(session, settings.timezone),
        artifact_root=settings.artifact_root,
        artifact_max_bytes=settings.artifact_max_bytes,
        checkpointer=request.app.state.poster_checkpointer,
    )


@router.post("/workflows")
def start_poster_workflow(
    payload: PosterWorkflowStart,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    thread_id = f"poster_{uuid4().hex}"
    return _poster_runner(request, session).advance(
        thread_id,
        input_state={
            "item_ids": payload.item_ids,
            "max_chars": payload.max_chars,
            "status": "running",
            "card_ids": [],
            "rendered_artifact_ids": [],
            "errors": [],
        },
    )


@router.post("/workflows/{thread_id}/resume")
def resume_poster_workflow(
    thread_id: str,
    payload: PosterWorkflowResume,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    return _poster_runner(request, session).advance(
        thread_id,
        approval=payload.approved,
    )


@router.post(
    "/generate",
    response_model=CardGenerateResult,
    status_code=status.HTTP_201_CREATED,
)
def generate_cards(
    payload: CardGenerateInput,
    request: Request,
    session: Session = Depends(get_session),
) -> CardGenerateResult:
    result = build_capability_executor(
        session,
        request.app.state.settings,
    ).execute(
        "poster.draft.generate",
        payload,
        ExecutionContext(
            request_id=f"req_{uuid4().hex}",
            actor_type="user",
        ),
    )
    return CardGenerateResult.model_validate(result)


@router.get("", response_model=CardPage)
def list_cards(
    request: Request,
    day: date | None = Query(default=None),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    priority: Priority | None = Query(default=None),
    source_kind: SourceKind | None = Query(default=None),
    topic: str | None = Query(default=None),
    session: Session = Depends(get_session),
) -> CardPage:
    return CardService(session, request.app.state.settings.timezone).list(
        day=day,
        month=month,
        priority=priority,
        source_kind=source_kind,
        topic=topic,
    )


@router.get("/{card_id}", response_model=CardRead)
def get_card(
    card_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> CardRead:
    try:
        return CardService(
            session,
            request.app.state.settings.timezone,
        ).get(card_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{card_id}", response_model=CardRead)
def update_card(
    card_id: str,
    payload: CardUpdateInput,
    request: Request,
    session: Session = Depends(get_session),
) -> CardRead:
    try:
        return CardService(
            session,
            request.app.state.settings.timezone,
        ).update(card_id, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{card_id}/render", response_model=CardRenderResult)
def render_card(
    card_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> CardRenderResult:
    try:
        return CardService(
            session,
            request.app.state.settings.timezone,
        ).render(
            card_id,
            artifact_root=request.app.state.settings.artifact_root,
            artifact_max_bytes=(
                request.app.state.settings.artifact_max_bytes
            ),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
