from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    CollectionRunModel,
    IntelligenceItemModel,
    RawItemModel,
    SourceConfigModel,
)
from ai_signal_api.modules.collection.collectors import (
    CollectedItem,
    CollectorRegistry,
)
from ai_signal_api.modules.intelligence.service import (
    Analyzer,
    HeuristicAnalyzer,
)


TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "ref",
    "source",
    "utm_campaign",
    "utm_content",
    "utm_medium",
    "utm_source",
    "utm_term",
}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS
        )
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            query,
            "",
        )
    )


class SourceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self) -> list[SourceConfigModel]:
        return list(
            self.session.scalars(
                select(SourceConfigModel).order_by(SourceConfigModel.created_at)
            )
        )

    def create(
        self,
        *,
        name: str,
        kind: str,
        config: dict,
        enabled: bool,
    ) -> SourceConfigModel:
        source = SourceConfigModel(
            name=name,
            kind=kind,
            config=config,
            enabled=enabled,
        )
        self.session.add(source)
        self.session.commit()
        return source

    def patch(self, source_id: str, values: dict) -> SourceConfigModel:
        source = self.session.get(SourceConfigModel, source_id)
        if source is None:
            raise LookupError("SOURCE_NOT_FOUND")
        for key, value in values.items():
            setattr(source, key, value)
        self.session.commit()
        return source


class CollectionService:
    def __init__(
        self,
        session: Session,
        collectors: CollectorRegistry | None = None,
        analyzer: Analyzer | None = None,
    ) -> None:
        self.session = session
        self.collectors = collectors or CollectorRegistry()
        self.analyzer = analyzer or HeuristicAnalyzer()

    def start(self, source_ids: list[str] | None = None) -> CollectionRunModel:
        requested_ids = source_ids or []
        query = select(SourceConfigModel).where(
            SourceConfigModel.enabled.is_(True)
        )
        if requested_ids:
            query = query.where(SourceConfigModel.id.in_(requested_ids))
        sources = list(self.session.scalars(query))

        run = CollectionRunModel(
            status="running",
            source_ids=[source.id for source in sources],
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.commit()

        if not sources:
            run.status = "failed"
            run.errors = [
                {
                    "error_code": "NO_ENABLED_SOURCES",
                    "message": "No enabled sources are available.",
                }
            ]
            run.completed_at = datetime.now(timezone.utc)
            self.session.commit()
            return run

        errors: list[dict[str, str]] = []
        collected_count = 0
        added_count = 0
        successful_source_count = 0

        for source in sources:
            try:
                collector = self.collectors.resolve(source.kind)
                items = collector.collect(source.config)
                successful_source_count += 1
                collected_count += len(items)
                for item in items:
                    if self._persist_item(run, source, item):
                        added_count += 1
            except Exception as error:  # noqa: BLE001
                errors.append(
                    {
                        "source_id": source.id,
                        "source_name": source.name,
                        "error_code": self._error_code(error),
                        "message": str(error),
                    }
                )

        run.items_collected = collected_count
        run.items_added = added_count
        run.errors = errors
        run.completed_at = datetime.now(timezone.utc)
        if errors and successful_source_count:
            run.status = "partial"
        elif errors:
            run.status = "failed"
        else:
            run.status = "completed"
        self.session.commit()
        return run

    @staticmethod
    def _error_code(error: Exception) -> str:
        if isinstance(error, KeyError):
            return "SOURCE_CONFIG_INVALID"
        if isinstance(error, httpx.TimeoutException):
            return "SOURCE_TIMEOUT"
        if isinstance(error, httpx.HTTPStatusError):
            return "SOURCE_HTTP_ERROR"
        return "SOURCE_COLLECTION_FAILED"

    def get_run(self, run_id: str) -> CollectionRunModel:
        run = self.session.get(CollectionRunModel, run_id)
        if run is None:
            raise LookupError("RUN_NOT_FOUND")
        return run

    def list_runs(self, limit: int = 30) -> list[CollectionRunModel]:
        return list(
            self.session.scalars(
                select(CollectionRunModel)
                .order_by(CollectionRunModel.created_at.desc())
                .limit(limit)
            )
        )

    def _persist_item(
        self,
        run: CollectionRunModel,
        source: SourceConfigModel,
        item: CollectedItem,
    ) -> bool:
        canonical_url = canonicalize_url(item.url)
        existing = self.session.scalar(
            select(RawItemModel).where(
                RawItemModel.canonical_url == canonical_url
            )
        )
        if existing is not None:
            return False

        raw_item = RawItemModel(
            run_id=run.id,
            source_id=source.id,
            external_id=item.external_id,
            title=item.title,
            url=item.url,
            canonical_url=canonical_url,
            description=item.description,
            published_at=item.published_at,
        )
        analysis = self.analyzer.analyze(item)
        raw_item.intelligence = IntelligenceItemModel(
            summary=analysis.summary,
            topics=analysis.topics,
            priority=analysis.priority,
        )
        self.session.add(raw_item)
        self.session.commit()
        return True


def seed_demo_sources(session: Session) -> None:
    existing_count = session.scalar(select(SourceConfigModel.id).limit(1))
    if existing_count is not None:
        return
    session.add_all(
        [
            SourceConfigModel(
                name="OpenAI 官方",
                kind="demo",
                config={"dataset": "openai"},
            ),
            SourceConfigModel(
                name="LangChain 官方",
                kind="demo",
                config={"dataset": "langgraph"},
            ),
            SourceConfigModel(
                name="GitHub Release",
                kind="demo",
                config={"dataset": "whisperlive"},
            ),
        ]
    )
    session.commit()


def seed_live_sources(session: Session) -> None:
    """Seed a small, editable set of real AI sources for local workspaces."""
    defaults = (
        {
            "name": "OpenAI 官方动态",
            "kind": "rss",
            "config": {
                "url": "https://openai.com/news/rss.xml",
                "limit": 20,
            },
        },
        {
            "name": "LangGraph Releases",
            "kind": "github_releases",
            "config": {
                "repository": "langchain-ai/langgraph",
                "limit": 10,
            },
        },
        {
            "name": "Transformers Releases",
            "kind": "github_releases",
            "config": {
                "repository": "huggingface/transformers",
                "limit": 10,
            },
        },
    )
    existing = {
        source.name: source
        for source in session.scalars(select(SourceConfigModel))
    }
    added_default = False
    for values in defaults:
        if values["name"] not in existing:
            session.add(
                SourceConfigModel(
                    name=values["name"],
                    kind=values["kind"],
                    config=values["config"],
                    enabled=True,
                )
            )
            added_default = True

    if added_default:
        for source in existing.values():
            if source.kind == "demo":
                source.enabled = False
    session.commit()
