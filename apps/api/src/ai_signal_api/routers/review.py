from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.modules.review.service import ReviewService
from ai_signal_api.schemas import (
    ExecutionContext,
    ReviewBatchRead,
    ReviewSubmitInput,
)


router = APIRouter(prefix="/api/review-batches", tags=["review"])


@router.get("/current", response_model=ReviewBatchRead)
def current_review_batch(
    session: Session = Depends(get_session),
) -> ReviewBatchRead:
    return ReviewService(session).current()


@router.get("/{batch_id}", response_model=ReviewBatchRead)
def get_review_batch(
    batch_id: str,
    session: Session = Depends(get_session),
) -> ReviewBatchRead:
    try:
        return ReviewService(session).read(batch_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{batch_id}/decisions", response_model=ReviewBatchRead)
def submit_review_batch(
    batch_id: str,
    payload: ReviewSubmitInput,
    request: Request,
    session: Session = Depends(get_session),
) -> ReviewBatchRead:
    result = build_capability_executor(
        session,
        request.app.state.settings,
    ).execute(
        "review.batch.submit",
        payload.model_copy(update={"batch_id": batch_id}),
        ExecutionContext(
            request_id=f"req_{uuid4().hex}",
            actor_type="user",
        ),
    )
    return ReviewBatchRead.model_validate(result)
