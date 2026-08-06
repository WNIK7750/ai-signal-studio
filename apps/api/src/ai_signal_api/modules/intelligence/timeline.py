from collections import defaultdict
import base64
import binascii
from datetime import datetime
import json

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    IntelligenceItemModel,
    RawItemModel,
    SourceConfigModel,
    TaskRunItemModel,
    WorkspaceItemStateModel,
)
from ai_signal_api.schemas import TimelineItem, TimelinePage, TimelineQuery


class TimelineService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def query(self, filters: TimelineQuery) -> TimelinePage:
        conditions = []
        cursor_published_at: datetime | None = None
        cursor_item_id: str | None = None
        if filters.cursor:
            try:
                padding = "=" * (-len(filters.cursor) % 4)
                payload = json.loads(
                    base64.urlsafe_b64decode(
                        f"{filters.cursor}{padding}"
                    ).decode("utf-8")
                )
                cursor_published_at = datetime.fromisoformat(payload["at"])
                cursor_item_id = str(payload["id"])
            except (
                binascii.Error,
                KeyError,
                TypeError,
                UnicodeDecodeError,
                ValueError,
                json.JSONDecodeError,
            ) as error:
                raise ValueError("TIMELINE_CURSOR_INVALID") from error
        if filters.search:
            search = f"%{filters.search.strip()}%"
            conditions.append(
                or_(
                    RawItemModel.title.ilike(search),
                    IntelligenceItemModel.summary.ilike(search),
                    SourceConfigModel.name.ilike(search),
                    cast(IntelligenceItemModel.topics, String).ilike(search),
                )
            )
        if filters.priority:
            conditions.append(
                IntelligenceItemModel.priority == filters.priority
            )
        if filters.source_kind:
            conditions.append(SourceConfigModel.kind == filters.source_kind)
        if filters.source_ids:
            conditions.append(SourceConfigModel.id.in_(filters.source_ids))
        if filters.topics:
            topic_conditions = [
                cast(IntelligenceItemModel.topics, String).ilike(
                    f"%{topic}%"
                )
                for topic in filters.topics
            ]
            conditions.append(or_(*topic_conditions))
        if filters.published_from:
            conditions.append(
                RawItemModel.published_at >= filters.published_from
            )
        if filters.published_to:
            conditions.append(
                RawItemModel.published_at <= filters.published_to
            )
        if filters.starred is True:
            conditions.append(WorkspaceItemStateModel.starred.is_(True))
        elif filters.starred is False:
            conditions.append(
                or_(
                    WorkspaceItemStateModel.id.is_(None),
                    WorkspaceItemStateModel.starred.is_(False),
                )
            )
        if filters.seen is True:
            conditions.append(WorkspaceItemStateModel.seen_at.is_not(None))
        elif filters.seen is False:
            conditions.append(WorkspaceItemStateModel.seen_at.is_(None))
        if filters.archived is True:
            conditions.append(
                WorkspaceItemStateModel.archived_at.is_not(None)
            )
        elif filters.archived is False:
            conditions.append(WorkspaceItemStateModel.archived_at.is_(None))
        cursor_conditions = []
        if cursor_published_at is not None and cursor_item_id is not None:
            if filters.sort == "oldest":
                cursor_conditions.append(
                    or_(
                        RawItemModel.published_at > cursor_published_at,
                        and_(
                            RawItemModel.published_at
                            == cursor_published_at,
                            IntelligenceItemModel.id > cursor_item_id,
                        ),
                    )
                )
            else:
                cursor_conditions.append(
                    or_(
                        RawItemModel.published_at < cursor_published_at,
                        and_(
                            RawItemModel.published_at
                            == cursor_published_at,
                            IntelligenceItemModel.id < cursor_item_id,
                        ),
                    )
                )

        base = (
            select(
                IntelligenceItemModel,
                RawItemModel,
                SourceConfigModel,
                WorkspaceItemStateModel,
            )
            .join(
                RawItemModel,
                RawItemModel.id == IntelligenceItemModel.raw_item_id,
            )
            .join(
                SourceConfigModel,
                SourceConfigModel.id == RawItemModel.source_id,
            )
            .outerjoin(
                WorkspaceItemStateModel,
                WorkspaceItemStateModel.intelligence_item_id
                == IntelligenceItemModel.id,
            )
            .where(*conditions, *cursor_conditions)
        )
        if filters.task_id:
            base = base.join(
                TaskRunItemModel,
                TaskRunItemModel.intelligence_item_id
                == IntelligenceItemModel.id,
            ).where(TaskRunItemModel.task_id == filters.task_id)
        base = base.distinct()
        count_statement = (
            select(func.count(func.distinct(IntelligenceItemModel.id)))
            .select_from(IntelligenceItemModel)
            .join(
                RawItemModel,
                RawItemModel.id == IntelligenceItemModel.raw_item_id,
            )
            .join(
                SourceConfigModel,
                SourceConfigModel.id == RawItemModel.source_id,
            )
            .outerjoin(
                WorkspaceItemStateModel,
                WorkspaceItemStateModel.intelligence_item_id
                == IntelligenceItemModel.id,
            )
            .where(*conditions)
        )
        if filters.task_id:
            count_statement = count_statement.join(
                TaskRunItemModel,
                TaskRunItemModel.intelligence_item_id
                == IntelligenceItemModel.id,
            ).where(TaskRunItemModel.task_id == filters.task_id)
        total = int(self.session.scalar(count_statement) or 0)
        if filters.sort == "oldest":
            ordering = (
                RawItemModel.published_at.asc(),
                IntelligenceItemModel.id.asc(),
            )
        else:
            ordering = (
                RawItemModel.published_at.desc(),
                IntelligenceItemModel.id.desc(),
            )
        statement = base.order_by(*ordering)
        if filters.cursor is None:
            statement = statement.offset(filters.offset)
        rows = self.session.execute(
            statement.limit(filters.limit + 1)
        ).all()
        has_more = len(rows) > filters.limit
        rows = rows[: filters.limit]
        item_ids = [intelligence.id for intelligence, *_ in rows]
        task_map: dict[str, set[str]] = defaultdict(set)
        if item_ids:
            for intelligence_id, task_id in self.session.execute(
                select(
                    TaskRunItemModel.intelligence_item_id,
                    TaskRunItemModel.task_id,
                ).where(
                    TaskRunItemModel.intelligence_item_id.in_(item_ids),
                    TaskRunItemModel.task_id.is_not(None),
                )
            ):
                task_map[intelligence_id].add(task_id)

        next_cursor = None
        if has_more and rows:
            last_intelligence, last_raw, *_ = rows[-1]
            cursor_payload = json.dumps(
                {
                    "at": last_raw.published_at.isoformat(),
                    "id": last_intelligence.id,
                },
                separators=(",", ":"),
            ).encode("utf-8")
            next_cursor = base64.urlsafe_b64encode(cursor_payload).decode(
                "ascii"
            ).rstrip("=")

        return TimelinePage(
            total=total,
            has_more=has_more,
            next_cursor=next_cursor,
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
                    task_ids=sorted(task_map[intelligence.id]),
                    seen=bool(state and state.seen_at),
                    starred=bool(state and state.starred),
                    archived=bool(state and state.archived_at),
                    note=state.note if state else "",
                )
                for intelligence, raw, source, state in rows
            ],
        )
