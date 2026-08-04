from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.models import CommonPlanModel, ScheduledTaskModel


def calculate_next_run(
    time_of_day: str,
    timezone_name: str,
    now: datetime | None = None,
) -> datetime:
    timezone = ZoneInfo(timezone_name)
    local_now = (now or datetime.now(timezone)).astimezone(timezone)
    hour, minute = (int(value) for value in time_of_day.split(":"))
    candidate = local_now.replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if candidate <= local_now:
        candidate += timedelta(days=1)
    return candidate


class AutomationService:
    def __init__(self, session: Session, timezone_name: str) -> None:
        self.session = session
        self.timezone_name = timezone_name

    def list_plans(self) -> list[CommonPlanModel]:
        return list(
            self.session.scalars(
                select(CommonPlanModel).order_by(CommonPlanModel.created_at)
            )
        )

    def create_plan(self, values: dict) -> CommonPlanModel:
        plan = CommonPlanModel(**values)
        self.session.add(plan)
        self.session.commit()
        return plan

    def patch_plan(self, plan_id: str, values: dict) -> CommonPlanModel:
        plan = self.session.get(CommonPlanModel, plan_id)
        if plan is None:
            raise LookupError("PLAN_NOT_FOUND")
        for key, value in values.items():
            setattr(plan, key, value)
        self.session.commit()
        return plan

    def list_tasks(self) -> list[ScheduledTaskModel]:
        return list(
            self.session.scalars(
                select(ScheduledTaskModel).order_by(
                    ScheduledTaskModel.created_at
                )
            )
        )

    def create_task(self, values: dict) -> ScheduledTaskModel:
        if self.session.get(CommonPlanModel, values["plan_id"]) is None:
            raise LookupError("PLAN_NOT_FOUND")
        task = ScheduledTaskModel(
            **values,
            next_run_at=(
                calculate_next_run(
                    values["time_of_day"],
                    self.timezone_name,
                )
                if values.get("enabled", True)
                else None
            ),
        )
        self.session.add(task)
        self.session.commit()
        return task

    def patch_task(self, task_id: str, values: dict) -> ScheduledTaskModel:
        task = self.session.get(ScheduledTaskModel, task_id)
        if task is None:
            raise LookupError("TASK_NOT_FOUND")
        for key, value in values.items():
            setattr(task, key, value)
        task.next_run_at = (
            calculate_next_run(task.time_of_day, self.timezone_name)
            if task.enabled
            else None
        )
        self.session.commit()
        return task


def seed_common_plans(session: Session) -> None:
    existing = session.scalar(select(CommonPlanModel.id).limit(1))
    if existing is not None:
        return
    session.add_all(
        [
            CommonPlanModel(
                name="每日 AI 要闻",
                prompt="收集过去 24 小时内的重要 AI 信息",
                topics=["AI 要闻", "行业动态"],
            ),
            CommonPlanModel(
                name="Agent 与 Coding",
                prompt="收集 Agent 与 AI Coding 相关的重要信息",
                topics=["Agent", "AI Coding"],
            ),
            CommonPlanModel(
                name="开源模型更新",
                prompt="收集开源模型与工具更新",
                topics=["开源模型", "模型与工具"],
            ),
        ]
    )
    session.commit()

