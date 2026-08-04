from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.cards.service import CardService
from ai_signal_api.schemas import (
    CardGenerateInput,
    CardGenerateResult,
    CardPage,
    CardRead,
    ExecutionContext,
    Priority,
    SourceKind,
)


router = APIRouter(prefix="/api/cards", tags=["cards"])


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
