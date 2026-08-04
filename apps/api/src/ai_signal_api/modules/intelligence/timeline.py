from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    IntelligenceItemModel,
    RawItemModel,
    SourceConfigModel,
)
from ai_signal_api.schemas import TimelineItem, TimelinePage, TimelineQuery


class TimelineService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def query(self, filters: TimelineQuery) -> TimelinePage:
        conditions = []
        if filters.search:
            search = f"%{filters.search.strip()}%"
            conditions.append(
                or_(
                    RawItemModel.title.ilike(search),
                    IntelligenceItemModel.summary.ilike(search),
                    SourceConfigModel.name.ilike(search),
                )
            )
        if filters.priority:
            conditions.append(
                IntelligenceItemModel.priority == filters.priority
            )
        if filters.source_kind:
            conditions.append(SourceConfigModel.kind == filters.source_kind)

        base = (
            select(
                IntelligenceItemModel,
                RawItemModel,
                SourceConfigModel,
            )
            .join(
                RawItemModel,
                RawItemModel.id == IntelligenceItemModel.raw_item_id,
            )
            .join(
                SourceConfigModel,
                SourceConfigModel.id == RawItemModel.source_id,
            )
            .where(*conditions)
        )
        count_statement = (
            select(func.count())
            .select_from(IntelligenceItemModel)
            .join(
                RawItemModel,
                RawItemModel.id == IntelligenceItemModel.raw_item_id,
            )
            .join(
                SourceConfigModel,
                SourceConfigModel.id == RawItemModel.source_id,
            )
            .where(*conditions)
        )
        total = int(self.session.scalar(count_statement) or 0)
        rows = self.session.execute(
            base.order_by(RawItemModel.published_at.desc())
            .offset(filters.offset)
            .limit(filters.limit)
        ).all()

        return TimelinePage(
            total=total,
            items=[
                TimelineItem(
                    id=intelligence.id,
                    title=raw.title,
                    summary=intelligence.summary,
                    canonical_url=raw.canonical_url,
                    source_id=source.id,
                    source_name=source.name,
                    source_kind=source.kind,
                    published_at=raw.published_at,
                    topics=intelligence.topics,
                    priority=intelligence.priority,
                )
                for intelligence, raw, source in rows
            ],
        )

