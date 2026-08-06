from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    CollectionRunModel,
    IntelligenceItemModel,
    RawItemModel,
    SourceConfigModel,
    SourceRunResultModel,
    SourceVersionModel,
    TaskRunItemModel,
)
from ai_signal_api.modules.collection.collectors import (
    CollectedItem,
    CollectorRegistry,
)
from ai_signal_api.modules.intelligence.service import (
    AnalysisResult,
    Analyzer,
    HeuristicAnalyzer,
)
from ai_signal_api.schemas import (
    SourceCreate,
    SourcePatch,
    TaskConfig,
    TaskPreviewResult,
    TaskPreviewSample,
    TaskRunRead,
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


@dataclass(frozen=True, slots=True)
class TaskCandidate:
    source: SourceConfigModel
    item: CollectedItem
    analysis: AnalysisResult
    canonical_url: str
    matched_rules: list[str]


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
    def __init__(
        self,
        session: Session,
        collectors: CollectorRegistry | None = None,
    ) -> None:
        self.session = session
        self.collectors = collectors or CollectorRegistry()

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
        definition = SourceCreate.model_validate(
            {
                "name": name,
                "kind": kind,
                "config": config,
                "enabled": enabled,
            }
        )
        source = SourceConfigModel(
            name=definition.name,
            kind=definition.kind,
            config=definition.config,
            enabled=definition.enabled,
        )
        self.session.add(source)
        self.session.commit()
        return source

    def patch(self, source_id: str, values: dict) -> SourceConfigModel:
        source = self.session.get(SourceConfigModel, source_id)
        if source is None:
            raise LookupError("SOURCE_NOT_FOUND")
        patch = SourcePatch.model_validate(values)
        changes = patch.model_dump(exclude_unset=True)
        definition = SourceCreate.model_validate(
            {
                "name": changes.get("name", source.name),
                "kind": source.kind,
                "config": changes.get("config", source.config),
                "enabled": changes.get("enabled", source.enabled),
            }
        )
        for key in changes:
            setattr(source, key, getattr(definition, key))
        self.session.commit()
        return source

    def test(self, source_id: str) -> dict[str, object]:
        source = self.session.get(SourceConfigModel, source_id)
        if source is None:
            raise LookupError("SOURCE_NOT_FOUND")
        result = self.test_definition(
            SourceCreate(
                name=source.name,
                kind=source.kind,
                config=source.config,
                enabled=source.enabled,
            ),
            source_id=source.id,
        )
        now = datetime.now(timezone.utc)
        if result["status"] == "error":
            source.health_status = "error"
            source.last_error_at = now
            source.last_error_code = str(result["error_code"])
            self.session.commit()
            return result
        source.health_status = "healthy"
        source.last_success_at = now
        source.last_error_code = None
        source.last_items_count = int(result["items_count"])
        self.session.commit()
        return result

    def test_definition(
        self,
        definition: SourceCreate,
        *,
        source_id: str | None = None,
    ) -> dict[str, object]:
        try:
            items = self.collectors.resolve(definition.kind).collect(
                definition.config
            )
            if not items:
                raise ValueError("SOURCE_EMPTY")
        except Exception as error:
            error_code = self._source_error_code(error)
            return {
                "source_id": source_id,
                "status": "error",
                "items_count": 0,
                "sample_titles": [],
                "error_code": error_code,
            }
        return {
            "source_id": source_id,
            "status": "healthy",
            "items_count": len(items),
            "sample_titles": [item.title for item in items[:3]],
            "error_code": None,
        }

    @staticmethod
    def _source_error_code(error: Exception) -> str:
        stable_value_errors = {
            "SOURCE_URL_UNSAFE",
            "SOURCE_URL_PRIVATE_ADDRESS",
            "SOURCE_REDIRECT_LIMIT",
            "SOURCE_REDIRECT_INVALID",
            "SOURCE_CONTENT_TYPE_UNSUPPORTED",
            "SOURCE_RESPONSE_TOO_LARGE",
        }
        if str(error) in stable_value_errors:
            return str(error)
        if isinstance(error, (TimeoutError, httpx.TimeoutException)):
            return "SOURCE_TIMEOUT"
        if isinstance(error, httpx.HTTPStatusError):
            status_code = error.response.status_code
            if status_code == 401:
                return "SOURCE_UNAUTHORIZED"
            if status_code == 429:
                return "SOURCE_RATE_LIMITED"
            return "SOURCE_HTTP_ERROR"
        if isinstance(error, httpx.ConnectError):
            return "SOURCE_DNS_FAILED"
        if str(error) == "SOURCE_EMPTY":
            return "SOURCE_EMPTY"
        if isinstance(error, (json.JSONDecodeError, ValueError)):
            return "SOURCE_PARSE_FAILED"
        return "SOURCE_TEST_FAILED"


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

    def start(
        self,
        source_ids: list[str] | None = None,
        *,
        idempotency_key: str | None = None,
        trigger_type: str = "manual",
    ) -> CollectionRunModel:
        if idempotency_key:
            existing = self.session.scalar(
                select(CollectionRunModel).where(
                    CollectionRunModel.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                return existing
        requested_ids = source_ids or []
        query = select(SourceConfigModel).where(
            SourceConfigModel.enabled.is_(True)
        )
        if requested_ids:
            query = query.where(SourceConfigModel.id.in_(requested_ids))
        sources = list(self.session.scalars(query))

        run = CollectionRunModel(
            status="running",
            trigger_type=trigger_type,
            idempotency_key=idempotency_key,
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
        run.funnel_counts = {
            "fetched": collected_count,
            "matched": collected_count,
            "deduplicated": added_count,
            "selected": added_count,
        }
        run.coverage_status = "met"
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

    def ingest_discovered_items(
        self,
        source_items: list[tuple[SourceConfigModel, CollectedItem]],
        *,
        idempotency_key: str | None,
        trigger_type: str,
    ) -> tuple[CollectionRunModel, list[str]]:
        if idempotency_key:
            existing = self.session.scalar(
                select(CollectionRunModel).where(
                    CollectionRunModel.idempotency_key == idempotency_key
                )
            )
            if existing is not None:
                information_ids = list(
                    self.session.scalars(
                        select(IntelligenceItemModel.id)
                        .join(
                            RawItemModel,
                            RawItemModel.id
                            == IntelligenceItemModel.raw_item_id,
                        )
                        .where(RawItemModel.run_id == existing.id)
                    )
                )
                return existing, information_ids
        source_ids = list(
            dict.fromkeys(source.id for source, _item in source_items)
        )
        run = CollectionRunModel(
            status="running",
            coverage_status="met",
            trigger_type=trigger_type,
            idempotency_key=idempotency_key,
            source_ids=source_ids,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.commit()
        information_ids: list[str] = []
        for source, item in source_items:
            if self._persist_item(run, source, item):
                information = self.session.scalar(
                    select(IntelligenceItemModel)
                    .join(
                        RawItemModel,
                        RawItemModel.id
                        == IntelligenceItemModel.raw_item_id,
                    )
                    .where(
                        RawItemModel.canonical_url
                        == canonicalize_url(item.url)
                    )
                )
                if information is not None:
                    information_ids.append(information.id)
        run.items_collected = len(source_items)
        run.items_added = len(information_ids)
        run.funnel_counts = {
            "fetched": len(source_items),
            "matched": len(source_items),
            "deduplicated": len(information_ids),
            "selected": len(information_ids),
        }
        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        self.session.commit()
        return run, information_ids

    def resolve_task_sources(
        self,
        config: TaskConfig,
    ) -> list[SourceConfigModel]:
        selection = config.sources
        query = select(SourceConfigModel).where(
            SourceConfigModel.enabled.is_(True)
        )
        if selection.mode == "selected":
            if not selection.include_ids:
                return []
            query = query.where(
                SourceConfigModel.id.in_(selection.include_ids)
            )
        if selection.exclude_ids:
            query = query.where(
                SourceConfigModel.id.not_in(selection.exclude_ids)
            )
        return list(
            self.session.scalars(
                query.order_by(SourceConfigModel.created_at)
            )
        )

    def preview_task(self, config: TaskConfig) -> TaskPreviewResult:
        selected, funnel, _metrics, errors = self._evaluate_task(config)
        warnings = []
        if len(selected) < config.quantity.min_items:
            warnings.append("TASK_MIN_ITEMS_NOT_MET")
        if errors:
            warnings.append("TASK_SOURCE_PARTIAL")
        return TaskPreviewResult(
            funnel_counts=funnel,
            samples=[
                TaskPreviewSample(
                    title=candidate.item.title,
                    source_name=candidate.source.name,
                    published_at=candidate.item.published_at,
                    priority=candidate.analysis.priority,
                    reason="、".join(candidate.matched_rules)
                    or "符合任务规则",
                )
                for candidate in selected[:5]
            ],
            warning_codes=warnings,
        )

    def start_task(
        self,
        *,
        task_id: str,
        task_version_id: str,
        config: TaskConfig,
        trigger_type: str,
        parent_run_id: str | None = None,
    ) -> CollectionRunModel:
        sources = self.resolve_task_sources(config)
        run = CollectionRunModel(
            status="running",
            coverage_status="unknown",
            task_id=task_id,
            task_version_id=task_version_id,
            trigger_type=trigger_type,
            parent_run_id=parent_run_id,
            source_ids=[source.id for source in sources],
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(run)
        self.session.flush()

        selected, funnel, metrics, errors = self._evaluate_task(
            config,
            sources=sources,
        )
        source_versions = {
            source.id: self._ensure_source_version(source)
            for source in sources
        }
        run.source_version_ids = [
            version.id for version in source_versions.values()
        ]

        added_count = 0
        for rank, candidate in enumerate(selected, start=1):
            intelligence, added = self._persist_task_candidate(
                run,
                candidate,
            )
            added_count += int(added)
            self.session.add(
                TaskRunItemModel(
                    run_id=run.id,
                    task_id=task_id,
                    intelligence_item_id=intelligence.id,
                    matched_rules=candidate.matched_rules,
                    rank=rank,
                )
            )

        successful_sources = 0
        for source in sources:
            values = metrics[source.id]
            error = next(
                (
                    item
                    for item in errors
                    if item.get("source_id") == source.id
                ),
                None,
            )
            status = "failed" if error else "completed"
            if not error:
                successful_sources += 1
                source.health_status = "healthy"
                source.last_success_at = datetime.now(timezone.utc)
                source.last_error_code = None
                source.last_items_count = values["fetched"]
            else:
                source.health_status = "error"
                source.last_error_at = datetime.now(timezone.utc)
                source.last_error_code = str(error["error_code"])
            self.session.add(
                SourceRunResultModel(
                    run_id=run.id,
                    source_id=source.id,
                    source_version_id=source_versions[source.id].id,
                    status=status,
                    fetched_count=values["fetched"],
                    matched_count=values["matched"],
                    duplicate_count=values["duplicate"],
                    selected_count=values["selected"],
                    error_code=(
                        str(error["error_code"]) if error else None
                    ),
                    error_message=str(error["message"]) if error else None,
                )
            )

        if errors and successful_sources:
            run.status = "partial"
        elif errors or not sources:
            run.status = "failed"
        else:
            run.status = "completed"
        run.coverage_status = (
            "unknown"
            if run.status == "failed"
            else (
                "met"
                if funnel["selected"] >= config.quantity.min_items
                else "insufficient"
            )
        )
        warnings: list[str] = []
        if run.coverage_status == "insufficient":
            warnings.append("TASK_MIN_ITEMS_NOT_MET")
        if run.status == "partial":
            warnings.append("TASK_SOURCE_PARTIAL")
        run.warning_codes = warnings
        run.items_collected = funnel["fetched"]
        run.items_added = added_count
        run.funnel_counts = funnel
        run.errors = errors or (
            [
                {
                    "error_code": "TASK_NO_ENABLED_SOURCE",
                    "message": "No enabled source matched the task.",
                }
            ]
            if not sources
            else []
        )
        run.completed_at = datetime.now(timezone.utc)
        self.session.commit()
        return run

    def read_task_run(self, run: CollectionRunModel) -> TaskRunRead:
        source_results = list(
            self.session.scalars(
                select(SourceRunResultModel)
                .where(SourceRunResultModel.run_id == run.id)
                .order_by(SourceRunResultModel.id)
            )
        )
        return TaskRunRead.model_validate(run).model_copy(
            update={"source_results": source_results}
        )

    def _evaluate_task(
        self,
        config: TaskConfig,
        *,
        sources: list[SourceConfigModel] | None = None,
    ) -> tuple[
        list[TaskCandidate],
        dict[str, int],
        dict[str, dict[str, int]],
        list[dict[str, str]],
    ]:
        resolved_sources = sources or self.resolve_task_sources(config)
        metrics = {
            source.id: {
                "fetched": 0,
                "matched": 0,
                "duplicate": 0,
                "selected": 0,
            }
            for source in resolved_sources
        }
        errors: list[dict[str, str]] = []
        matched: list[TaskCandidate] = []
        for source in resolved_sources:
            try:
                collector = self.collectors.resolve(source.kind)
                items = collector.collect(source.config)[
                    : config.sources.per_source_max_items
                ]
                metrics[source.id]["fetched"] = len(items)
                for item in items:
                    analysis = self.analyzer.analyze(item)
                    rules = self._match_rules(config, item, analysis)
                    if rules is None:
                        continue
                    metrics[source.id]["matched"] += 1
                    matched.append(
                        TaskCandidate(
                            source=source,
                            item=item,
                            analysis=analysis,
                            canonical_url=canonicalize_url(item.url),
                            matched_rules=rules,
                        )
                    )
            except Exception as error:  # noqa: BLE001
                errors.append(
                    {
                        "source_id": source.id,
                        "source_name": source.name,
                        "error_code": self._error_code(error),
                        "message": str(error),
                    }
                )

        unique: dict[str, TaskCandidate] = {}
        for candidate in matched:
            if candidate.canonical_url in unique:
                metrics[candidate.source.id]["duplicate"] += 1
                continue
            unique[candidate.canonical_url] = candidate
        priority_order = {"important": 0, "watch": 1, "normal": 2}
        ordered = sorted(
            unique.values(),
            key=lambda candidate: (
                priority_order.get(candidate.analysis.priority, 3),
                -candidate.item.published_at.timestamp(),
                candidate.canonical_url,
            ),
        )
        selected = ordered[: config.quantity.max_items]
        for candidate in selected:
            metrics[candidate.source.id]["selected"] += 1
        funnel = {
            "fetched": sum(value["fetched"] for value in metrics.values()),
            "matched": len(matched),
            "deduplicated": len(unique),
            "selected": len(selected),
        }
        return selected, funnel, metrics, errors

    @staticmethod
    def _match_rules(
        config: TaskConfig,
        item: CollectedItem,
        analysis: AnalysisResult,
    ) -> list[str] | None:
        published_at = item.published_at
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        earliest = datetime.now(timezone.utc) - timedelta(
            hours=config.time_window.lookback_hours
        )
        if published_at.astimezone(timezone.utc) < earliest:
            return None

        matching = config.matching
        value = (
            item.title
            if matching.search_scope == "title"
            else f"{item.title} {item.description}"
        ).casefold()
        include_any = [
            term.casefold() for term in matching.include_any if term.strip()
        ]
        include_all = [
            term.casefold() for term in matching.include_all if term.strip()
        ]
        exclude = [
            term.casefold() for term in matching.exclude if term.strip()
        ]
        if include_any and not any(term in value for term in include_any):
            return None
        if include_all and not all(term in value for term in include_all):
            return None
        if exclude and any(term in value for term in exclude):
            return None
        if matching.topics and not (
            set(matching.topics).intersection(analysis.topics)
            or any(topic.casefold() in value for topic in matching.topics)
        ):
            return None
        if analysis.priority not in config.importance.accepted_levels:
            return None
        quality = config.quality_requirements
        if quality.require_source_link and not item.url.strip():
            return None
        if quality.require_extractable_content and not (
            item.title.strip() or item.description.strip()
        ):
            return None
        rules = []
        if include_any:
            rules.append("包含任一关键词")
        if include_all:
            rules.append("包含全部关键词")
        if matching.topics:
            rules.append("主题匹配")
        rules.append("重要程度符合")
        return rules

    def _ensure_source_version(
        self,
        source: SourceConfigModel,
    ) -> SourceVersionModel:
        snapshot = {
            "kind": source.kind,
            "config": source.config,
            "enabled": source.enabled,
        }
        digest = hashlib.sha256(
            json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        existing = self.session.scalar(
            select(SourceVersionModel).where(
                SourceVersionModel.source_id == source.id,
                SourceVersionModel.config_hash == digest,
            )
        )
        if existing is not None:
            return existing
        version_number = int(
            self.session.scalar(
                select(func.max(SourceVersionModel.version_number)).where(
                    SourceVersionModel.source_id == source.id
                )
            )
            or 0
        )
        version = SourceVersionModel(
            source_id=source.id,
            version_number=version_number + 1,
            adapter_type=source.kind,
            config_snapshot=snapshot,
            config_hash=digest,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def _persist_task_candidate(
        self,
        run: CollectionRunModel,
        candidate: TaskCandidate,
    ) -> tuple[IntelligenceItemModel, bool]:
        existing = self.session.scalar(
            select(RawItemModel).where(
                RawItemModel.canonical_url == candidate.canonical_url
            )
        )
        if existing is not None and existing.intelligence is not None:
            return existing.intelligence, False
        raw_item = RawItemModel(
            run_id=run.id,
            source_id=candidate.source.id,
            external_id=candidate.item.external_id,
            title=candidate.item.title,
            url=candidate.item.url,
            canonical_url=candidate.canonical_url,
            description=candidate.item.description,
            published_at=candidate.item.published_at,
        )
        intelligence = IntelligenceItemModel(
            summary=candidate.analysis.summary,
            topics=candidate.analysis.topics,
            priority=candidate.analysis.priority,
        )
        raw_item.intelligence = intelligence
        self.session.add(raw_item)
        self.session.flush()
        return intelligence, True

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
