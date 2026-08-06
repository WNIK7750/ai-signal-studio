from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_signal_api.models import (
    CollectionRunModel,
    CollectionTaskModel,
    CollectionTaskVersionModel,
)
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.schemas import (
    TaskConfig,
    TaskCreate,
    TaskPatch,
    TaskPreviewResult,
    TaskRead,
    TaskRunRead,
)


def _config_hash(config: dict) -> str:
    encoded = json.dumps(
        config,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _next_run(config: TaskConfig, status: str) -> datetime | None:
    schedule = config.schedule
    if status != "enabled" or schedule.mode == "manual":
        return None
    timezone = ZoneInfo(config.time_window.timezone)
    now = datetime.now(timezone)
    if schedule.mode == "interval" and schedule.interval_hours:
        return now + timedelta(hours=schedule.interval_hours)
    hour, minute = (int(value) for value in schedule.time_of_day.split(":"))
    candidate = now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    if schedule.mode in {"weekdays", "weekly"}:
        allowed = set(schedule.weekdays or range(5))
        while candidate.weekday() not in allowed:
            candidate += timedelta(days=1)
    return candidate


class TaskingService:
    def __init__(
        self,
        session: Session,
        collection: CollectionService,
    ) -> None:
        self.session = session
        self.collection = collection

    def list_tasks(self) -> list[TaskRead]:
        tasks = list(
            self.session.scalars(
                select(CollectionTaskModel).order_by(
                    CollectionTaskModel.pinned.desc(),
                    CollectionTaskModel.updated_at.desc(),
                )
            )
        )
        return [self._read(task) for task in tasks]

    def get_task(self, task_id: str) -> TaskRead:
        return self._read(self._get(task_id))

    def create_task(self, payload: TaskCreate) -> TaskRead:
        self._validate_sources(payload.config)
        task = CollectionTaskModel(
            name=payload.name,
            goal=payload.goal,
            status=payload.status,
            pinned=payload.pinned,
        )
        self.session.add(task)
        self.session.flush()
        version = self._create_version(task, payload.config, "")
        task.latest_version_id = version.id
        if payload.status == "enabled":
            task.active_version_id = version.id
        task.next_run_at = _next_run(payload.config, task.status)
        self.session.commit()
        return self._read(task)

    def patch_task(self, task_id: str, payload: TaskPatch) -> TaskRead:
        task = self._get(task_id)
        if payload.name is not None:
            task.name = payload.name
        if payload.goal is not None:
            task.goal = payload.goal
        if payload.pinned is not None:
            task.pinned = payload.pinned
        if payload.status is not None:
            task.status = payload.status

        config = payload.config or self._active_config(task)
        if payload.config is not None:
            self._validate_sources(config)
            version = self._create_version(
                task,
                config,
                payload.change_note,
            )
            task.latest_version_id = version.id
            if task.status == "enabled":
                task.active_version_id = version.id
        elif task.status == "enabled" and task.active_version_id is None:
            task.active_version_id = task.latest_version_id
        task.next_run_at = _next_run(config, task.status)
        self.session.commit()
        return self._read(task)

    def preview(
        self,
        task_id: str,
        config: TaskConfig | None = None,
    ) -> TaskPreviewResult:
        task = self._get(task_id)
        return self.collection.preview_task(config or self._active_config(task))

    def run(
        self,
        task_id: str,
        *,
        task_version_id: str | None = None,
        trigger_type: str = "manual",
        parent_run_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> TaskRunRead:
        if idempotency_key:
            existing = self.session.scalar(
                select(CollectionRunModel).where(
                    CollectionRunModel.task_id == task_id,
                    CollectionRunModel.idempotency_key == idempotency_key,
                )
            )
            if existing is not None:
                return self.collection.read_task_run(existing)
        task = self._get(task_id)
        version_id = (
            task_version_id
            or task.active_version_id
            or task.latest_version_id
        )
        if version_id is None:
            raise LookupError("TASK_VERSION_NOT_FOUND")
        version = self.session.get(CollectionTaskVersionModel, version_id)
        if version is None or version.task_id != task.id:
            raise LookupError("TASK_VERSION_NOT_FOUND")
        config = TaskConfig.model_validate(version.config_snapshot)
        run = self.collection.start_task(
            task_id=task.id,
            task_version_id=version.id,
            config=config,
            trigger_type=trigger_type,
            parent_run_id=parent_run_id,
        )
        run.idempotency_key = idempotency_key
        task.last_run_at = run.completed_at or run.created_at
        task.next_run_at = _next_run(config, task.status)
        self.session.commit()
        return self.collection.read_task_run(run)

    def get_run(self, run_id: str) -> TaskRunRead:
        return self.collection.read_task_run(
            self.collection.get_run(run_id)
        )

    def retry_run(
        self,
        run_id: str,
        *,
        mode: str = "original_version",
    ) -> TaskRunRead:
        original = self.collection.get_run(run_id)
        if original.task_id is None:
            raise ValueError("RUN_IS_NOT_TASK_RUN")
        version_id = (
            original.task_version_id
            if mode == "original_version"
            else None
        )
        return self.run(
            original.task_id,
            task_version_id=version_id,
            trigger_type="retry",
            parent_run_id=original.id,
        )

    def _create_version(
        self,
        task: CollectionTaskModel,
        config: TaskConfig,
        change_note: str,
    ) -> CollectionTaskVersionModel:
        snapshot = config.model_dump(mode="json")
        current_number = int(
            self.session.scalar(
                select(
                    func.max(CollectionTaskVersionModel.version_number)
                ).where(CollectionTaskVersionModel.task_id == task.id)
            )
            or 0
        )
        version = CollectionTaskVersionModel(
            task_id=task.id,
            version_number=current_number + 1,
            config_snapshot=snapshot,
            config_hash=_config_hash(snapshot),
            change_note=change_note,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def _read(self, task: CollectionTaskModel) -> TaskRead:
        version_id = task.latest_version_id or task.active_version_id
        version = (
            self.session.get(CollectionTaskVersionModel, version_id)
            if version_id
            else None
        )
        return TaskRead(
            id=task.id,
            name=task.name,
            goal=task.goal,
            status=task.status,
            latest_version_id=task.latest_version_id,
            active_version_id=task.active_version_id,
            pinned=task.pinned,
            version_number=version.version_number if version else None,
            config=(
                TaskConfig.model_validate(version.config_snapshot)
                if version
                else None
            ),
            last_run_at=task.last_run_at,
            next_run_at=task.next_run_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    def _active_config(self, task: CollectionTaskModel) -> TaskConfig:
        version_id = task.latest_version_id or task.active_version_id
        if version_id is None:
            raise LookupError("TASK_VERSION_NOT_FOUND")
        version = self.session.get(CollectionTaskVersionModel, version_id)
        if version is None:
            raise LookupError("TASK_VERSION_NOT_FOUND")
        return TaskConfig.model_validate(version.config_snapshot)

    def _get(self, task_id: str) -> CollectionTaskModel:
        task = self.session.get(CollectionTaskModel, task_id)
        if task is None:
            raise LookupError("TASK_NOT_FOUND")
        return task

    def _validate_sources(self, config: TaskConfig) -> None:
        sources = self.collection.resolve_task_sources(config)
        if not sources:
            raise ValueError("TASK_NO_ENABLED_SOURCE")
