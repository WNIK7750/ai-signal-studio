from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.config import Settings
from ai_signal_api.models import (
    CommonPlanModel,
    CollectionTaskModel,
    CollectionTaskVersionModel,
    ScheduledTaskModel,
)
from ai_signal_api.schemas import (
    CollectionRunStart,
    ExecutionContext,
    TaskConfig,
    TaskRunCapabilityInput,
)


def build_scheduler(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> tuple[
    BackgroundScheduler,
    Callable[[str], None],
    Callable[[str], None],
]:
    scheduler = BackgroundScheduler(timezone=settings.timezone)

    def execute_task(task_id: str) -> None:
        with session_factory() as session:
            task = session.get(ScheduledTaskModel, task_id)
            if task is None or not task.enabled:
                return
            plan = session.get(CommonPlanModel, task.plan_id)
            if plan is None:
                return
            build_capability_executor(session, settings).execute(
                "collection.run.start",
                CollectionRunStart(source_ids=plan.source_ids),
                ExecutionContext(
                    request_id=f"schedule_{uuid4().hex}",
                    actor_type="system",
                    actor_id="scheduler",
                    idempotency_key=f"{task.id}:{datetime.now(timezone.utc):%Y-%m-%d}",
                ),
            )
            task.last_run_at = datetime.now(timezone.utc)
            session.commit()

    def sync_task(task_id: str) -> None:
        with session_factory() as session:
            task = session.get(ScheduledTaskModel, task_id)
            job_id = f"scheduled-task:{task_id}"
            if scheduler.get_job(job_id) is not None:
                scheduler.remove_job(job_id)
            if task is None or not task.enabled:
                return
            hour, minute = (
                int(value) for value in task.time_of_day.split(":")
            )
            scheduler.add_job(
                execute_task,
                CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=settings.timezone,
                ),
                args=[task.id],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

    def execute_collection_task(task_id: str) -> None:
        with session_factory() as session:
            task = session.get(CollectionTaskModel, task_id)
            if (
                task is None
                or task.status != "enabled"
                or task.active_version_id is None
            ):
                return
            build_capability_executor(session, settings).execute(
                "task.run.start",
                TaskRunCapabilityInput(
                    task_id=task.id,
                    task_version_id=task.active_version_id,
                    trigger_type="schedule",
                ),
                ExecutionContext(
                    request_id=f"schedule_{uuid4().hex}",
                    actor_type="system",
                    actor_id="scheduler",
                    idempotency_key=(
                        f"{task.id}:{task.active_version_id}:"
                        f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M}"
                    ),
                ),
            )

    def sync_collection_task(task_id: str) -> None:
        with session_factory() as session:
            task = session.get(CollectionTaskModel, task_id)
            job_id = f"collection-task:{task_id}"
            if scheduler.get_job(job_id) is not None:
                scheduler.remove_job(job_id)
            if (
                task is None
                or task.status != "enabled"
                or task.active_version_id is None
            ):
                return
            version = session.get(
                CollectionTaskVersionModel,
                task.active_version_id,
            )
            if version is None:
                return
            config = TaskConfig.model_validate(version.config_snapshot)
            schedule = config.schedule
            if schedule.mode == "manual":
                return
            if schedule.mode == "interval" and schedule.interval_hours:
                trigger = IntervalTrigger(
                    hours=schedule.interval_hours,
                    timezone=config.time_window.timezone,
                )
            else:
                hour, minute = (
                    int(value)
                    for value in schedule.time_of_day.split(":")
                )
                day_of_week = None
                if schedule.mode == "weekdays":
                    day_of_week = "mon-fri"
                elif schedule.mode == "weekly":
                    weekdays = schedule.weekdays or [0]
                    names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
                    day_of_week = ",".join(names[day] for day in weekdays)
                trigger = CronTrigger(
                    hour=hour,
                    minute=minute,
                    day_of_week=day_of_week,
                    timezone=config.time_window.timezone,
                )
            scheduler.add_job(
                execute_collection_task,
                trigger,
                args=[task.id],
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

    with session_factory() as session:
        task_ids = list(
            session.scalars(
                select(ScheduledTaskModel.id).where(
                    ScheduledTaskModel.enabled.is_(True)
                )
            )
        )
    for task_id in task_ids:
        sync_task(task_id)

    with session_factory() as session:
        collection_task_ids = list(
            session.scalars(
                select(CollectionTaskModel.id).where(
                    CollectionTaskModel.status == "enabled"
                )
            )
        )
    for task_id in collection_task_ids:
        sync_collection_task(task_id)

    return scheduler, sync_task, sync_collection_task
