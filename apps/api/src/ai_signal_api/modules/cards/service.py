from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
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
    CardRenderResult,
    CardUpdateInput,
)
from ai_signal_api.modules.agent_assets.artifacts import ArtifactService


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
                cover_variant=int(
                    hashlib.sha256(item.id.encode("utf-8")).hexdigest(),
                    16,
                )
                % 6,
                cover_url=self._source_cover_url(raw.source.config),
                cover_source=(
                    "original"
                    if self._source_cover_url(raw.source.config)
                    else "offline"
                ),
                template_id=(
                    "offline-quote"
                    if int(
                        hashlib.sha256(item.id.encode("utf-8")).hexdigest(),
                        16,
                    )
                    % 2
                    == 0
                    else "offline-grid"
                ),
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

    def update(
        self,
        card_id: str,
        payload: CardUpdateInput,
    ) -> CardRead:
        card = self.session.get(CardModel, card_id)
        if card is None:
            raise LookupError("CARD_NOT_FOUND")
        if card.revision != payload.expected_revision:
            raise ValueError("CARD_REVISION_CONFLICT")
        card.title = payload.title
        card.summary = payload.summary
        card.key_points = payload.key_points
        card.template_id = payload.template_id
        card.cover_source = payload.cover_source
        if payload.cover_source == "offline":
            card.cover_url = None
        card.revision += 1
        card.render_status = "not_rendered"
        card.rendered_artifact_id = None
        card.rendered_revision = None
        self.session.commit()
        return self._read(card)

    def render(
        self,
        card_id: str,
        *,
        artifact_root,
        artifact_max_bytes: int,
    ) -> CardRenderResult:
        card = self.session.get(CardModel, card_id)
        if card is None:
            raise LookupError("CARD_NOT_FOUND")
        if (
            card.render_status == "rendered"
            and card.rendered_artifact_id
            and card.rendered_revision == card.revision
        ):
            return CardRenderResult(
                card_id=card.id,
                artifact_id=card.rendered_artifact_id,
                status="rendered",
            )
        card.render_status = "rendering"
        self.session.commit()
        try:
            png = _render_offline_png(card)
            artifact = ArtifactService(
                self.session,
                artifact_root,
                artifact_max_bytes,
            ).create(
                filename=f"{card.id}-r{card.revision}.png",
                media_type="image/png",
                content_base64=base64.b64encode(png).decode("ascii"),
                metadata={
                    "artifact_kind": "rendered_card",
                    "source_title": card.source_name,
                    "source_url": card.canonical_url,
                    "source_time": card.published_at.isoformat(),
                    "card_id": card.id,
                },
            )
            card.render_status = "rendered"
            card.rendered_artifact_id = artifact.id
            card.rendered_revision = card.revision
            self.session.commit()
            return CardRenderResult(
                card_id=card.id,
                artifact_id=artifact.id,
                status="rendered",
            )
        except Exception:
            card.render_status = "failed"
            self.session.commit()
            raise

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
            revision=card.revision,
            template_id=card.template_id,
            cover_source=card.cover_source,
            render_status=card.render_status,
            rendered_artifact_id=card.rendered_artifact_id,
        )


def _render_offline_png(card: CardModel) -> bytes:
    project_root = Path(__file__).resolve().parents[6]
    renderer = (
        project_root / "vendor_tools/poster_renderer/render-poster.mjs"
    )
    node = shutil.which("node")
    if node is None or not renderer.exists():
        raise RuntimeError("POSTER_RENDERER_UNAVAILABLE")
    payload = {
        "variant": card.cover_variant,
        "template_id": card.template_id,
        "title": card.title,
        "summary": card.summary,
        "key_points": card.key_points,
        "source_name": card.source_name,
    }
    result = subprocess.run(
        [node, str(renderer)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
    )
    if result.returncode != 0 or not result.stdout.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        detail = result.stderr.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"POSTER_RENDER_FAILED: {detail}")
    return result.stdout
