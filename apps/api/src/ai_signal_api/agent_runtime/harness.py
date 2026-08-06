from __future__ import annotations

import hashlib
import json
import sqlite3
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ai_signal_api.agent_runtime.contracts import (
    AgentPlan,
    AgentTurnCreate,
    AgentTurnRead,
    AgentTurnResult,
    ErrorEnvelope,
    ExecutionManifest,
)
from ai_signal_api.agent_runtime.graph import WorkspaceGraphRunner
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.config import Settings
from ai_signal_api.models import (
    AgentConversationModel,
    AgentMessageModel,
    AgentResultBlockModel,
    AgentTurnEventModel,
    AgentTurnModel,
    AgentTurnStepModel,
    new_id,
)
from ai_signal_api.modules.models.service import (
    ModelConfigurationService,
)


TERMINAL_STATUSES = {"complete", "partial", "failed", "cancelled"}


class RecoveryScanner:
    """Finds abandoned local turns without replaying completed side effects."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def scan(self, now: datetime | None = None) -> list[str]:
        current = now or datetime.now(timezone.utc)
        turns = list(
            self.session.scalars(
                select(AgentTurnModel).where(
                    AgentTurnModel.status == "running"
                )
            )
        )
        recovered: list[str] = []
        for turn in turns:
            expires_at = turn.lease_expires_at
            if expires_at is None:
                continue
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > current:
                continue
            turn.status = "queued"
            turn.lease_owner = None
            turn.lease_expires_at = None
            recovered.append(turn.id)
        self.session.commit()
        return recovered


def _fixture_plan(message: str = "") -> dict[str, Any]:
    if not (
        ("收集" in message or "采集" in message)
        and "推荐" in message
    ):
        card_id_match = re.search(r"\bcard_[a-zA-Z0-9]+\b", message)
        if card_id_match and any(
            keyword in message for keyword in ("渲染", "PNG", "海报")
        ):
            capability_id = "poster.card.render"
            arguments = {"card_id": card_id_match.group(0)}
            selected_domains = ["cards"]
            objective = "渲染指定卡片并返回可下载 Artifact"
        elif any(keyword in message for keyword in ("文档", "附件", "Artifact")):
            capability_id = "artifact.search"
            arguments = {"query": "官方", "limit": 10}
            selected_domains = ["agent_assets"]
            objective = "检索本地 Artifact 并返回可定位引用"
        elif any(
            keyword in message
            for keyword in ("偏好", "长期记忆", "Agent Pack")
        ):
            capability_id = "agent_pack.search"
            arguments = {"pack_id": "ai-editor", "query": "偏好"}
            selected_domains = ["agent_assets"]
            objective = "按需检索已激活 Agent Pack"
        else:
            selected_domains = ["intelligence"]
            objective = "基于已保存信息完成可追溯研究"
            capability_id = (
                "research.compare"
                if "比较" in message
                else "research.trend_brief"
                if "趋势" in message
                else "research.match_requirements"
                if any(
                    keyword in message
                    for keyword in ("开源", "Windows", "本地部署", "官方证据")
                )
                else "research.filter"
                if "筛选" in message
                else "research.recommend"
            )
            arguments = {
                "topic": "Agent",
                "lookback_days": 30,
                "limit": 5,
            }
        if capability_id == "research.compare":
            arguments["compare_terms"] = [
                "OpenAI",
                "LangGraph",
                "WhisperLive",
            ]
        if capability_id == "research.match_requirements":
            arguments["requirements"] = [
                "开源",
                "本地部署",
                "Windows",
                "官方证据",
            ]
        return {
            "objective": objective,
            "constraints": {"max_items": 5},
            "assumptions": [],
            "planning_mode": "dynamic",
            "selected_domains": selected_domains,
            "steps": [
                {
                    "step_id": "research",
                    "title": "研究已保存信息",
                    "goal": "返回带站内引用的结构化研究结果",
                    "kind": "domain_agent",
                    "domains": selected_domains,
                    "capability_id": capability_id,
                    "arguments": arguments,
                    "dependencies": [],
                    "success_criteria": "事实包含真实 information_id",
                    "acceptance_policy": {
                        "id": "information_results.v1",
                        "params": {"min_items": 0},
                    },
                    "side_effect": "read",
                    "risk": "low",
                    "failure_policy": "continue_independent",
                }
            ],
            "max_replans": 2,
        }
    return {
        "objective": "收集最近 24 小时的 AI 信息并推荐 Agent 内容",
        "constraints": {"lookback_hours": 24, "max_items": 5},
        "assumptions": [],
        "planning_mode": "dynamic",
        "selected_domains": ["collection", "intelligence"],
        "steps": [
            {
                "step_id": "collect",
                "title": "采集信息",
                "goal": "采集启用来源",
                "kind": "capability",
                "domains": ["collection"],
                "capability_id": "collection.run.start",
                "dependencies": [],
                "success_criteria": "至少一个来源完成",
                "acceptance_policy": {
                    "id": "capability_effect.v1",
                    "params": {},
                },
                "side_effect": "external",
                "risk": "low",
                "failure_policy": "continue_independent",
            },
            {
                "step_id": "query",
                "title": "查询与筛选",
                "goal": "查询最近 24 小时信息",
                "kind": "capability",
                "domains": ["intelligence"],
                "capability_id": "intelligence.timeline.query",
                "dependencies": ["collect"],
                "success_criteria": "返回真实信息 ID",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 1},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "stop_dependents",
            },
            {
                "step_id": "recommend",
                "title": "推荐内容",
                "goal": "推荐最多 5 条 Agent 内容",
                "kind": "domain_agent",
                "domains": ["intelligence"],
                "capability_id": "intelligence.recommend",
                "dependencies": ["query"],
                "success_criteria": "每条含真实信息 ID 和来源",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 1},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "stop_dependents",
            },
        ],
        "max_replans": 2,
    }


class FixturePlannerChatModel(BaseChatModel):
    """Deterministic Fake Chat Model used only by demo/test workspaces."""

    @property
    def _llm_type(self) -> str:
        return "workspace-fixture-planner"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        user_message = next(
            (
                str(message.content)
                for message in reversed(messages)
                if getattr(message, "type", "") == "human"
            ),
            "",
        )
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=json.dumps(
                            _fixture_plan(user_message),
                            ensure_ascii=False,
                        )
                    )
                )
            ]
        )


def build_planner_model(
    settings: Settings,
    model_service: ModelConfigurationService,
    model_id: str | None,
) -> tuple[BaseChatModel, str]:
    selection = model_service.select_for_request(model_id)
    model = selection.effective_model
    if model.provider == "heuristic":
        if settings.source_seed_mode != "demo":
            raise RuntimeError("AGENT_MODEL_TOOL_CALLING_REQUIRED")
        return FixturePlannerChatModel(), model.id
    if not model.api_key:
        raise RuntimeError("AGENT_MODEL_NOT_CONFIGURED")
    return (
        ChatOpenAI(
            model=model.model_id,
            base_url=model.base_url,
            api_key=SecretStr(model.api_key),
            max_tokens=model.output_token_limit
            or settings.llm_max_output_tokens,
            timeout=settings.llm_timeout_seconds,
            temperature=0,
        ),
        model.id,
    )


def build_sqlite_checkpointer(path: Path) -> tuple[SqliteSaver, sqlite3.Connection]:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    checkpointer = SqliteSaver(connection)
    checkpointer.setup()
    return checkpointer, connection


class EventJournal:
    def __init__(self, session: Session, turn: AgentTurnModel) -> None:
        self.session = session
        self.turn = turn

    def append(
        self,
        event_type: str,
        data: dict[str, Any],
        step_id: str | None = None,
    ) -> AgentTurnEventModel:
        now = datetime.now(timezone.utc)
        started_at = self.turn.started_at or self.turn.created_at
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        calculated = max(0, int((now - started_at).total_seconds() * 1000))
        previous = int(
            self.session.scalar(
                select(func.max(AgentTurnEventModel.elapsed_ms)).where(
                    AgentTurnEventModel.turn_id == self.turn.id
                )
            )
            or 0
        )
        sequence = self.turn.last_event_sequence + 1
        event = AgentTurnEventModel(
            turn_id=self.turn.id,
            sequence=sequence,
            event_type=event_type,
            elapsed_ms=max(previous, calculated),
            step_id=step_id,
            data=data,
        )
        self.turn.last_event_sequence = sequence
        self.session.add(event)
        self._project_step(event_type, data, step_id, now)
        self.session.commit()
        return event

    def _project_step(
        self,
        event_type: str,
        data: dict[str, Any],
        step_id: str | None,
        now: datetime,
    ) -> None:
        if event_type == "plan.ready":
            plan = AgentPlan.model_validate(data["plan"])
            self.turn.plan = plan.model_dump(mode="json")
            for step in plan.steps:
                persisted = self.session.scalar(
                    select(AgentTurnStepModel).where(
                        AgentTurnStepModel.turn_id == self.turn.id,
                        AgentTurnStepModel.step_id == step.step_id,
                    )
                )
                if persisted is None:
                    persisted = AgentTurnStepModel(
                        turn_id=self.turn.id,
                        step_id=step.step_id,
                        title=step.title,
                        domain_ids=step.domains,
                        capability_id=step.capability_id,
                    )
                    self.session.add(persisted)
                else:
                    persisted.title = step.title
                    persisted.domain_ids = step.domains
                    persisted.capability_id = step.capability_id
                    persisted.status = "pending"
                    persisted.duration_ms = 0
                    persisted.error = None
                    persisted.started_at = None
                    persisted.completed_at = None
            return
        if not step_id:
            return
        step = self.session.scalar(
            select(AgentTurnStepModel).where(
                AgentTurnStepModel.turn_id == self.turn.id,
                AgentTurnStepModel.step_id == step_id,
            )
        )
        if step is None:
            return
        if event_type == "step.started":
            step.status = "running"
            step.started_at = now
        elif event_type == "tool.completed":
            step.status = str(data.get("status", "completed"))
            step.completed_at = now
            started = step.started_at or now
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            step.duration_ms = max(
                0,
                int((now - started).total_seconds() * 1000),
            )


class AgentTurnService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        conversation_id: str,
        payload: AgentTurnCreate,
        *,
        capability_ids: list[str],
    ) -> tuple[AgentTurnRead, bool]:
        conversation = self.session.get(
            AgentConversationModel,
            conversation_id,
        )
        if (
            conversation is None
            or conversation.status != "active"
            or conversation.deleted_at is not None
        ):
            raise LookupError("AGENT_CONVERSATION_NOT_FOUND")
        existing = self.session.scalar(
            select(AgentTurnModel).where(
                AgentTurnModel.conversation_id == conversation_id,
                AgentTurnModel.client_message_id
                == payload.client_message_id,
            )
        )
        if existing is not None:
            return AgentTurnRead.model_validate(existing), False
        request_id = new_id("req")
        turn_id = new_id("turn")
        digest = hashlib.sha256(
            json.dumps(sorted(capability_ids)).encode("utf-8")
        ).hexdigest()
        turn = AgentTurnModel(
            id=turn_id,
            conversation_id=conversation_id,
            request_id=request_id,
            client_message_id=payload.client_message_id,
            message=payload.message,
            manifest=ExecutionManifest(
                model_config_ref=payload.model_id or "workspace-default",
                capability_snapshot_digest=digest,
            ).model_dump(mode="json"),
        )
        user_message = AgentMessageModel(
            conversation_id=conversation_id,
            role="user",
            content=payload.message,
            client_message_id=payload.client_message_id,
            request_id=request_id,
            turn_id=turn.id,
        )
        now = datetime.now(timezone.utc)
        if (
            conversation.title_source == "auto"
            and conversation.last_message_at is None
        ):
            title = " ".join(payload.message.split())
            conversation.title = (
                title if len(title) <= 28 else f"{title[:28].rstrip()}…"
            )
        conversation.active_turn_id = turn.id
        conversation.last_message_at = now
        conversation.updated_at = now
        self.session.add_all([turn, user_message])
        self.session.flush()
        EventJournal(self.session, turn).append(
            "turn.created",
            {"status": "queued"},
        )
        return AgentTurnRead.model_validate(turn), True

    def read(self, turn_id: str) -> AgentTurnRead:
        turn = self.session.get(AgentTurnModel, turn_id)
        if turn is None:
            raise LookupError("AGENT_TURN_NOT_FOUND")
        return AgentTurnRead.model_validate(turn)

    def cancel(self, turn_id: str) -> AgentTurnRead:
        turn = self.session.get(AgentTurnModel, turn_id)
        if turn is None:
            raise LookupError("AGENT_TURN_NOT_FOUND")
        if turn.status not in TERMINAL_STATUSES:
            turn.cancel_requested = True
            self.session.commit()
        return AgentTurnRead.model_validate(turn)


def process_turn(
    session_factory: sessionmaker[Session],
    settings: Settings,
    model_service: ModelConfigurationService,
    checkpointer: SqliteSaver,
    turn_id: str,
    model_id: str | None,
    resume_payload: dict[str, Any] | None = None,
) -> None:
    with session_factory() as session:
        turn = session.get(AgentTurnModel, turn_id)
        if turn is None or turn.status in TERMINAL_STATUSES:
            return
        now = datetime.now(timezone.utc)
        if turn.lease_expires_at is not None:
            expires_at = turn.lease_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at > now and turn.lease_owner:
                return
        turn.lease_owner = f"local-worker-{uuid4().hex}"
        turn.lease_expires_at = now + timedelta(minutes=2)
        turn.deadline_at = now + timedelta(minutes=5)
        turn.status = "running"
        turn.started_at = now
        session.commit()
        journal = EventJournal(session, turn)
        try:
            executor = build_capability_executor(session, settings)
            planner_model, effective_model_id = build_planner_model(
                settings,
                model_service,
                model_id,
            )
            manifest = dict(turn.manifest)
            manifest["model_config_ref"] = effective_model_id
            manifest["domain_pack_versions"] = {
                "collection": "1.0.0",
                "intelligence": "1.0.0",
                "tasking": "1.0.0",
                "sources": "1.0.0",
                "runs": "1.0.0",
                "review": "1.0.0",
                "agent_assets": "1.0.0",
                "cards": "1.0.0",
                "models": "1.0.0",
                "agent": "1.0.0",
            }
            turn.manifest = manifest
            runner = WorkspaceGraphRunner(
                executor=executor,
                planner_model=planner_model,
                checkpointer=checkpointer,
                event_sink=journal.append,
                cancellation_checker=lambda candidate_turn_id: _is_cancelled(
                    session_factory,
                    candidate_turn_id,
                ),
            )
            state = (
                runner.resume(
                    turn_id=turn.id,
                    payload=resume_payload,
                )
                if resume_payload is not None
                else runner.advance(
                    turn_id=turn.id,
                    conversation_id=turn.conversation_id,
                    request_id=turn.request_id,
                    message=turn.message,
                    cancel_requested=turn.cancel_requested,
                    retry_count=int(manifest.get("retry_count", 0)),
                    retry_source_ids=list(
                        manifest.get("retry_source_ids", [])
                    ),
                )
            )
            if state.get("status") in {
                "waiting_input",
                "waiting_approval",
            }:
                turn.status = state["status"]
                turn.plan = state.get("plan", {})
                turn.lease_owner = None
                turn.lease_expires_at = None
                session.commit()
                journal.append(
                    f"turn.{state['status']}",
                    {
                        "status": state["status"],
                        "interrupt": state["interrupt"],
                    },
                )
                return
            result = AgentTurnResult.model_validate(state["result"])
            now = datetime.now(timezone.utc)
            turn.status = result.status
            turn.plan = result.plan.model_dump(mode="json")
            turn.completed_at = now
            turn.total_duration_ms = max(
                0,
                int((now - turn.started_at).total_seconds() * 1000),
            )
            result.total_duration_ms = turn.total_duration_ms
            turn.result = result.model_dump(mode="json")
            turn.lease_owner = None
            turn.lease_expires_at = None
            for position, block in enumerate(result.result_blocks):
                session.merge(
                    AgentResultBlockModel(
                        id=block.block_id,
                        turn_id=turn.id,
                        block_type=block.type,
                        title=block.title,
                        position=position,
                        data=block.data,
                    )
                )
            assistant = session.scalar(
                select(AgentMessageModel).where(
                    AgentMessageModel.turn_id == turn.id,
                    AgentMessageModel.role == "assistant",
                )
            )
            if assistant is None:
                assistant = AgentMessageModel(
                    conversation_id=turn.conversation_id,
                    role="assistant",
                    content=result.message,
                    request_id=turn.request_id,
                    turn_id=turn.id,
                )
                session.add(assistant)
            assistant.content = result.message
            assistant.capability_calls = [
                    {
                        "capability_id": step.capability_id,
                        "status": "completed",
                    }
                    for step in result.plan.steps
                ]
            assistant.result_data = result.model_dump(mode="json")
            assistant.error_code = (
                result.errors[0].code
                if result.status == "failed" and result.errors
                else None
            )
            assistant.effective_model_id = effective_model_id
            conversation = session.get(
                AgentConversationModel,
                turn.conversation_id,
            )
            if conversation is not None:
                conversation.active_turn_id = None
                conversation.last_message_at = now
                conversation.updated_at = now
            session.commit()
            terminal_event = {
                "complete": "turn.completed",
                "partial": "turn.partial",
                "failed": "turn.failed",
                "cancelled": "turn.cancelled",
            }[result.status]
            journal.append(
                terminal_event,
                {
                    "status": result.status,
                    "total_duration_ms": turn.total_duration_ms,
                },
            )
        except Exception as error:
            now = datetime.now(timezone.utc)
            envelope = ErrorEnvelope(
                code="AGENT_EXECUTION_FAILED",
                message=str(error),
                source="system",
            )
            turn.status = "failed"
            turn.lease_owner = None
            turn.lease_expires_at = None
            turn.error = envelope.model_dump(mode="json")
            turn.completed_at = now
            turn.total_duration_ms = max(
                0,
                int((now - turn.started_at).total_seconds() * 1000),
            )
            conversation = session.get(
                AgentConversationModel,
                turn.conversation_id,
            )
            if conversation is not None:
                conversation.active_turn_id = None
            session.add(
                AgentMessageModel(
                    conversation_id=turn.conversation_id,
                    role="assistant",
                    content="任务未完成，请查看可定位错误。",
                    request_id=turn.request_id,
                    turn_id=turn.id,
                    result_data={
                        "status": "failed",
                        "errors": [envelope.model_dump(mode="json")],
                    },
                    error_code=envelope.code,
                )
            )
            session.commit()
            journal.append(
                "turn.failed",
                {
                    "status": "failed",
                    "error": envelope.model_dump(mode="json"),
                    "total_duration_ms": turn.total_duration_ms,
                },
            )


def _is_cancelled(
    session_factory: sessionmaker[Session],
    turn_id: str,
) -> bool:
    with session_factory() as session:
        turn = session.get(AgentTurnModel, turn_id)
        return bool(turn is None or turn.cancel_requested)
