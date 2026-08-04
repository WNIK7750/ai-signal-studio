from __future__ import annotations

import secrets
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    CardModel,
    IntelligenceItemModel,
    ReviewDecisionModel,
)
from ai_signal_api.schemas import (
    CardGenerateInput,
    CardGenerateResult,
    CardPage,
    CardRead,
)


def _key_points(summary: str, topics: list[str]) -> list[str]:
    clauses = [
        clause.strip(" 。；;")
        for clause in summary.replace("；", "。").split("。")
        if clause.strip()
    ]
    result = clauses[:3]
    if len(result) < 2:
        result.extend(f"关注主题：{topic}" for topic in topics[: 3 - len(result)])
    return result or ["打开原文查看完整信息"]


def _fit_summary(summary: str, max_chars: int) -> str:
    compact = " ".join(summary.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1].rstrip('，。；; ')}…"


class CardService:
    def __init__(
        self,
        session: Session,
        timezone_name: str = "Asia/Shanghai",
    ) -> None:
        self.session = session
        self.timezone = ZoneInfo(timezone_name)

    def generate(self, payload: CardGenerateInput) -> CardGenerateResult:
        statement = (
            select(ReviewDecisionModel, IntelligenceItemModel)
            .join(
                IntelligenceItemModel,
                IntelligenceItemModel.id == ReviewDecisionModel.item_id,
            )
            .where(ReviewDecisionModel.decision == "keep")
        )
        if payload.item_ids:
            statement = statement.where(
                ReviewDecisionModel.item_id.in_(payload.item_ids)
            )
        created = 0
        existing = 0
        card_ids: list[str] = []
        for decision, item in self.session.execute(statement).all():
            card = self.session.scalar(
                select(CardModel).where(
                    CardModel.intelligence_item_id == item.id
                )
            )
            if card is not None:
                existing += 1
                card_ids.append(card.id)
                continue
            raw = item.raw_item
            title = decision.edited_title or raw.title
            summary = _fit_summary(
                decision.edited_summary or item.summary,
                payload.max_chars,
            )
            card = CardModel(
                intelligence_item_id=item.id,
                review_decision_id=decision.id,
                title=title,
                summary=summary,
                key_points=_key_points(summary, item.topics),
                cover_variant=secrets.randbelow(6),
                cover_url=self._source_cover_url(raw.source.config),
                source_name=raw.source.name,
                source_kind=raw.source.kind,
                canonical_url=raw.canonical_url,
                published_at=raw.published_at,
                priority=item.priority,
                topics=item.topics,
            )
            self.session.add(card)
            self.session.flush()
            card_ids.append(card.id)
            created += 1
        self.session.commit()
        return CardGenerateResult(
            created=created,
            existing=existing,
            card_ids=card_ids,
        )

    @staticmethod
    def _source_cover_url(config: dict[str, object]) -> str | None:
        value = config.get("cover_url")
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value
        return None

    def list(
        self,
        *,
        day: date | None = None,
        month: str | None = None,
        priority: str | None = None,
        source_kind: str | None = None,
        topic: str | None = None,
    ) -> CardPage:
        statement = select(CardModel)
        if day is not None:
            start, end = self._utc_range(day, day + timedelta(days=1))
            statement = statement.where(
                CardModel.published_at >= start,
                CardModel.published_at < end,
            )
        elif month:
            year, month_number = (int(value) for value in month.split("-"))
            start_day = date(year, month_number, 1)
            end_day = (
                date(year + 1, 1, 1)
                if month_number == 12
                else date(year, month_number + 1, 1)
            )
            start, end = self._utc_range(start_day, end_day)
            statement = statement.where(
                CardModel.published_at >= start,
                CardModel.published_at < end,
            )
        if priority:
            statement = statement.where(CardModel.priority == priority)
        if source_kind:
            statement = statement.where(CardModel.source_kind == source_kind)
        cards = list(
            self.session.scalars(
                statement.order_by(CardModel.published_at.desc())
            )
        )
        if topic:
            cards = [card for card in cards if topic in card.topics]
        return CardPage(
            total=len(cards),
            items=[self._read(card) for card in cards],
        )

    def get(self, card_id: str) -> CardRead:
        card = self.session.get(CardModel, card_id)
        if card is None:
            raise LookupError("CARD_NOT_FOUND")
        return self._read(card)

    def _utc_range(
        self,
        start_day: date,
        end_day: date,
    ) -> tuple[datetime, datetime]:
        start = datetime.combine(
            start_day,
            time.min,
            tzinfo=self.timezone,
        ).astimezone(timezone.utc)
        end = datetime.combine(
            end_day,
            time.min,
            tzinfo=self.timezone,
        ).astimezone(timezone.utc)
        return start, end

    def _read(self, card: CardModel) -> CardRead:
        published_at = card.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        published_at = published_at.astimezone(self.timezone)
        return CardRead(
            id=card.id,
            title=card.title,
            summary=card.summary,
            key_points=card.key_points,
            cover_variant=card.cover_variant,
            cover_url=card.cover_url,
            source_name=card.source_name,
            source_kind=card.source_kind,
            canonical_url=card.canonical_url,
            published_at=published_at,
            priority=card.priority,
            topics=card.topics,
        )
