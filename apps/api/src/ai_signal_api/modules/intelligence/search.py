from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    CardModel,
    IntelligenceItemModel,
    RawItemModel,
    ReviewBatchModel,
    SourceConfigModel,
    WorkspaceItemStateModel,
)


SearchScope = Literal["pending", "intelligence", "archived", "cards"]


class IntelligenceSearchInput(BaseModel):
    query: str = Field(default="", max_length=500)
    scopes: list[SearchScope] = Field(
        default_factory=lambda: ["intelligence"],
        min_length=1,
        max_length=4,
    )
    limit: int = Field(default=20, ge=1, le=50)
    published_from: datetime | None = None
    published_to: datetime | None = None
    topics: list[str] = Field(default_factory=list, max_length=12)
    candidate_ids: list[str] = Field(default_factory=list, max_length=200)


class IntelligenceSearchItem(BaseModel):
    information_id: str
    title: str
    summary: str
    source_id: str
    source_name: str
    source_kind: str
    source_url: str
    published_at: datetime
    priority: Literal["important", "watch", "normal"]
    topics: list[str] = Field(default_factory=list)
    scopes: list[SearchScope] = Field(default_factory=list)
    score: float
    ranking_signals: list[str] = Field(default_factory=list)
    duplicate_information_ids: list[str] = Field(default_factory=list)
    app_path: str


class IntelligenceSearchResult(BaseModel):
    status: Literal["completed"] = "completed"
    query: str
    total_candidates: int
    items: list[IntelligenceSearchItem] = Field(default_factory=list)
    algorithm: str = "fts5_bm25+rrf+simhash"


class UnifiedIntelligenceSearchService:
    """Search one document per intelligence item across product stages."""

    RRF_K = 60

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(
        self,
        filters: IntelligenceSearchInput,
    ) -> IntelligenceSearchResult:
        rows = self._documents(filters)
        if not rows:
            return IntelligenceSearchResult(
                query=filters.query,
                total_candidates=0,
            )

        lexical_ids = self._lexical_rank(rows, filters.query)
        recency_ids = [
            row["information_id"]
            for row in sorted(
                rows,
                key=lambda item: (
                    item["published_at"],
                    item["information_id"],
                ),
                reverse=True,
            )
        ]
        priority_order = {"important": 0, "watch": 1, "normal": 2}
        impact_ids = [
            row["information_id"]
            for row in sorted(
                rows,
                key=lambda item: (
                    priority_order[item["priority"]],
                    -item["published_at"].timestamp(),
                    item["information_id"],
                ),
            )
        ]
        stage_ids = [
            row["information_id"]
            for row in sorted(
                rows,
                key=lambda item: (
                    -len(set(filters.scopes).intersection(item["scopes"])),
                    -int("cards" in item["scopes"]),
                    item["information_id"],
                ),
            )
        ]
        rankings = [
            ("文本相关性", lexical_ids),
            ("发布时间", recency_ids),
            ("影响优先级", impact_ids),
            ("产品阶段", stage_ids),
        ]
        scores: defaultdict[str, float] = defaultdict(float)
        signals: defaultdict[str, list[str]] = defaultdict(list)
        for label, ranking in rankings:
            for rank, information_id in enumerate(ranking, start=1):
                scores[information_id] += 1 / (self.RRF_K + rank)
                if rank <= 5:
                    signals[information_id].append(label)

        ordered = sorted(
            rows,
            key=lambda item: (
                -scores[item["information_id"]],
                -item["published_at"].timestamp(),
                item["information_id"],
            ),
        )
        selected, duplicate_map = self._collapse_near_duplicates(
            ordered,
            scores,
            filters.limit,
        )
        return IntelligenceSearchResult(
            query=filters.query,
            total_candidates=len(rows),
            items=[
                IntelligenceSearchItem(
                    **row,
                    score=round(scores[row["information_id"]], 8),
                    ranking_signals=signals[row["information_id"]],
                    duplicate_information_ids=duplicate_map.get(
                        row["information_id"],
                        [],
                    ),
                    app_path=(
                        f"/timeline?focus={row['information_id']}"
                    ),
                )
                for row in selected
            ],
        )

    def _documents(
        self,
        filters: IntelligenceSearchInput,
    ) -> list[dict]:
        statement = (
            select(
                IntelligenceItemModel,
                RawItemModel,
                SourceConfigModel,
                WorkspaceItemStateModel,
                CardModel,
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
            .outerjoin(
                CardModel,
                CardModel.intelligence_item_id == IntelligenceItemModel.id,
            )
        )
        if filters.published_from is not None:
            statement = statement.where(
                RawItemModel.published_at >= filters.published_from
            )
        if filters.published_to is not None:
            statement = statement.where(
                RawItemModel.published_at <= filters.published_to
            )

        pending_ids: set[str] = set()
        for item_ids in self.session.scalars(
            select(ReviewBatchModel.item_ids).where(
                ReviewBatchModel.status == "pending"
            )
        ):
            pending_ids.update(str(item_id) for item_id in item_ids)

        requested = set(filters.scopes)
        candidate_ids = set(filters.candidate_ids)
        documents = []
        for intelligence, raw, source, state, card in self.session.execute(
            statement
        ):
            scopes: list[SearchScope] = ["intelligence"]
            if intelligence.id in pending_ids:
                scopes.append("pending")
            if state is not None and state.archived_at is not None:
                scopes.append("archived")
            if card is not None:
                scopes.append("cards")
            if not requested.intersection(scopes):
                continue
            if candidate_ids and intelligence.id not in candidate_ids:
                continue
            if filters.topics and not set(filters.topics).intersection(
                intelligence.topics
            ):
                continue
            card_text = ""
            if card is not None:
                card_text = " ".join(
                    [card.title, card.summary, *card.key_points]
                )
            documents.append(
                {
                    "information_id": intelligence.id,
                    "title": raw.title,
                    "summary": intelligence.summary,
                    "source_id": source.id,
                    "source_name": source.name,
                    "source_kind": source.kind,
                    "source_url": raw.canonical_url,
                    "published_at": self._aware(raw.published_at),
                    "priority": intelligence.priority,
                    "topics": list(intelligence.topics),
                    "scopes": scopes,
                    "_search_text": " ".join(
                        [
                            raw.title,
                            raw.description,
                            intelligence.summary,
                            " ".join(intelligence.topics),
                            source.name,
                            card_text,
                            state.note if state is not None else "",
                        ]
                    ),
                }
            )
        return documents

    def _lexical_rank(
        self,
        rows: list[dict],
        query: str,
    ) -> list[str]:
        normalized = " ".join(query.split()).strip()
        if not normalized:
            return [row["information_id"] for row in rows]
        if (
            self.session.bind is not None
            and self.session.bind.dialect.name == "sqlite"
        ):
            ranked = self._sqlite_fts_rank(rows, normalized)
            if ranked:
                return ranked
        folded = normalized.casefold()
        matched = [
            row
            for row in rows
            if folded in row["_search_text"].casefold()
        ]
        return [
            row["information_id"]
            for row in sorted(
                matched,
                key=lambda item: (
                    item["_search_text"].casefold().count(folded),
                    item["published_at"],
                ),
                reverse=True,
            )
        ]

    def _sqlite_fts_rank(
        self,
        rows: list[dict],
        query: str,
    ) -> list[str]:
        self.session.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS intelligence_search_fts
                USING fts5(
                    information_id UNINDEXED,
                    title,
                    summary,
                    topics,
                    source,
                    card_text,
                    tokenize='trigram'
                )
                """
            )
        )
        self.session.execute(text("DELETE FROM intelligence_search_fts"))
        for row in rows:
            self.session.execute(
                text(
                    """
                    INSERT INTO intelligence_search_fts(
                        information_id, title, summary, topics, source,
                        card_text
                    ) VALUES (
                        :information_id, :title, :summary, :topics, :source,
                        :card_text
                    )
                    """
                ),
                {
                    "information_id": row["information_id"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "topics": " ".join(row["topics"]),
                    "source": row["source_name"],
                    "card_text": row["_search_text"],
                },
            )
        tokens = [
            token
            for token in re.findall(r"[\w\u3400-\u9fff]+", query)
            if len(token) >= 3
        ]
        rows_by_id = {row["information_id"]: row for row in rows}
        ranked: list[str] = []
        if tokens:
            expression = " OR ".join(
                f'"{token.replace(chr(34), chr(34) * 2)}"'
                for token in tokens
            )
            try:
                ranked = [
                    str(information_id)
                    for information_id, _score in self.session.execute(
                        text(
                            """
                            SELECT information_id,
                                   bm25(
                                       intelligence_search_fts,
                                       8.0, 4.0, 2.5, 1.5, 1.0
                                   ) AS score
                            FROM intelligence_search_fts
                            WHERE intelligence_search_fts MATCH :query
                            ORDER BY score ASC
                            """
                        ),
                        {"query": expression},
                    )
                    if str(information_id) in rows_by_id
                ]
            except Exception:
                ranked = []
        folded = query.casefold()
        short_matches = [
            row["information_id"]
            for row in rows
            if folded in row["_search_text"].casefold()
        ]
        return list(dict.fromkeys([*ranked, *short_matches]))

    @classmethod
    def _collapse_near_duplicates(
        cls,
        rows: list[dict],
        scores: dict[str, float],
        limit: int,
    ) -> tuple[list[dict], dict[str, list[str]]]:
        selected: list[dict] = []
        hashes: dict[str, int] = {}
        duplicates: defaultdict[str, list[str]] = defaultdict(list)
        for row in rows:
            information_id = row["information_id"]
            fingerprint = cls._simhash(
                f"{row['title']} {row['summary']}"
            )
            duplicate_of = next(
                (
                    existing_id
                    for existing_id, existing_hash in hashes.items()
                    if (fingerprint ^ existing_hash).bit_count() <= 3
                ),
                None,
            )
            if duplicate_of is not None:
                duplicates[duplicate_of].append(information_id)
                scores[duplicate_of] += scores[information_id] * 0.1
                continue
            hashes[information_id] = fingerprint
            selected.append(row)
            if len(selected) >= limit:
                break
        return selected, dict(duplicates)

    @staticmethod
    def _simhash(value: str) -> int:
        normalized = re.sub(r"\s+", " ", value.casefold()).strip()
        tokens = {
            normalized[index : index + 3]
            for index in range(max(len(normalized) - 2, 1))
            if normalized[index : index + 3].strip()
        } or {normalized}
        vector = [0] * 64
        for token in tokens:
            digest = int.from_bytes(
                hashlib.blake2b(
                    token.encode("utf-8"),
                    digest_size=8,
                ).digest(),
                "big",
            )
            for bit in range(64):
                vector[bit] += 1 if digest & (1 << bit) else -1
        return sum(
            1 << bit for bit, weight in enumerate(vector) if weight >= 0
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
