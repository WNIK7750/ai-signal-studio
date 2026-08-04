from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    IntelligenceItemModel,
    ReviewBatchModel,
    ReviewDecisionModel,
)
from ai_signal_api.schemas import (
    ExecutionContext,
    ReviewBatchRead,
    ReviewItemRead,
    ReviewSubmitInput,
)


class ReviewService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def current(self) -> ReviewBatchRead:
        batch = self.session.scalar(
            select(ReviewBatchModel)
            .where(ReviewBatchModel.status == "pending")
            .order_by(ReviewBatchModel.created_at.desc())
        )
        if batch is None:
            decided_ids = set(
                self.session.scalars(
                    select(ReviewDecisionModel.item_id)
                ).all()
            )
            item_ids = [
                item_id
                for item_id in self.session.scalars(
                    select(IntelligenceItemModel.id).order_by(
                        IntelligenceItemModel.created_at.desc()
                    )
                )
                if item_id not in decided_ids
            ]
            if not item_ids:
                completed = self.session.scalar(
                    select(ReviewBatchModel)
                    .where(ReviewBatchModel.status == "completed")
                    .order_by(ReviewBatchModel.completed_at.desc())
                )
                if completed is not None:
                    return self.read(completed.id)
            batch = ReviewBatchModel(item_ids=item_ids)
            self.session.add(batch)
            self.session.commit()
        return self.read(batch.id)

    def read(self, batch_id: str) -> ReviewBatchRead:
        batch = self.session.get(ReviewBatchModel, batch_id)
        if batch is None:
            raise LookupError("REVIEW_BATCH_NOT_FOUND")
        items_by_id = {
            item.id: item
            for item in self.session.scalars(
                select(IntelligenceItemModel).where(
                    IntelligenceItemModel.id.in_(batch.item_ids)
                )
            )
        }
        decisions = {
            decision.item_id: decision
            for decision in self.session.scalars(
                select(ReviewDecisionModel).where(
                    ReviewDecisionModel.batch_id == batch.id
                )
            )
        }
        items: list[ReviewItemRead] = []
        for item_id in batch.item_ids:
            item = items_by_id.get(item_id)
            if item is None:
                continue
            raw = item.raw_item
            decision = decisions.get(item_id)
            items.append(
                ReviewItemRead(
                    id=item.id,
                    title=raw.title,
                    summary=item.summary,
                    canonical_url=raw.canonical_url,
                    source_name=raw.source.name,
                    source_kind=raw.source.kind,
                    published_at=raw.published_at,
                    topics=item.topics,
                    priority=item.priority,
                    decision=decision.decision if decision else None,
                    edited_title=decision.edited_title if decision else None,
                    edited_summary=(
                        decision.edited_summary if decision else None
                    ),
                    note=decision.note if decision else "",
                )
            )
        return ReviewBatchRead(
            id=batch.id,
            status=batch.status,
            items=items,
            created_at=batch.created_at,
            completed_at=batch.completed_at,
        )

    def submit(
        self,
        payload: ReviewSubmitInput,
        context: ExecutionContext,
    ) -> ReviewBatchRead:
        batch = (
            self.current()
            if payload.batch_id is None
            else self.read(payload.batch_id)
        )
        decisions = payload.decisions
        if payload.default_decision is not None:
            supplied_ids = {decision.item_id for decision in decisions}
            decisions = [
                *decisions,
                *[
                    {
                        "item_id": item.id,
                        "decision": payload.default_decision,
                    }
                    for item in batch.items
                    if item.id not in supplied_ids
                ],
            ]

        for decision_input in decisions:
            data = (
                decision_input
                if isinstance(decision_input, dict)
                else decision_input.model_dump()
            )
            if data["item_id"] not in {item.id for item in batch.items}:
                raise ValueError("REVIEW_ITEM_NOT_IN_BATCH")
            existing = self.session.scalar(
                select(ReviewDecisionModel).where(
                    ReviewDecisionModel.batch_id == batch.id,
                    ReviewDecisionModel.item_id == data["item_id"],
                )
            )
            if existing is None:
                existing = ReviewDecisionModel(
                    batch_id=batch.id,
                    item_id=data["item_id"],
                )
                self.session.add(existing)
            existing.decision = data["decision"]
            existing.edited_title = data.get("edited_title")
            existing.edited_summary = data.get("edited_summary")
            existing.note = data.get("note", "")
            existing.actor_type = context.actor_type
            existing.actor_id = context.actor_id

        model = self.session.get(ReviewBatchModel, batch.id)
        assert model is not None
        self.session.flush()
        decision_count = len(
            self.session.scalars(
                select(ReviewDecisionModel).where(
                    ReviewDecisionModel.batch_id == batch.id
                )
            ).all()
        )
        if payload.confirm:
            if decision_count != len(batch.items):
                raise ValueError("REVIEW_DECISIONS_INCOMPLETE")
            model.status = "completed"
            model.completed_at = datetime.now(timezone.utc)
        self.session.commit()
        return self.read(batch.id)
