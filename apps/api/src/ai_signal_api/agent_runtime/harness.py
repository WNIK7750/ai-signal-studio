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
    AcceptancePolicy,
    AgentGoalSpec,
    AgentPlan,
    AgentResultBlock,
    AgentTurnCreate,
    AgentTurnRead,
    AgentTurnResult,
    ErrorEnvelope,
    ExecutionManifest,
    GoalTimeWindow,
    PlanStep,
    WORKFLOW_VERSION,
)
from ai_signal_api.agent_runtime.graph import WorkspaceGraphRunner
from ai_signal_api.modules.agent_assets.agent_packs import (
    DEFAULT_RULES,
    DEFAULT_SKILLS,
    AgentPackError,
    AgentPackService,
)
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.config import Settings
from ai_signal_api.integrations.llm.compatibility import (
    resolve_openai_compatibility,
)
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
    ModelConfigurationError,
    ModelConfigurationService,
)


TERMINAL_STATUSES = {"complete", "partial", "failed", "cancelled"}


def _execution_error_envelope(error: Exception) -> ErrorEnvelope:
    if isinstance(error, ModelConfigurationError):
        return ErrorEnvelope(
            code=error.code,
            message=error.message,
            source="provider",
            user_action="请检查所选模型及提供商配置。",
        )
    normalized = str(error).casefold()
    if (
        "tool_choice" in normalized
        and "thinking mode" in normalized
    ):
        return ErrorEnvelope(
            code="PROVIDER-006",
            message=(
                "所选提供方在思考模式下不支持结构化工具选择；"
                "请使用兼容配置或关闭思考模式。"
            ),
            source="provider",
            user_action="请重新测试模型连接后重试。",
        )
    return ErrorEnvelope(
        code="AGENT_EXECUTION_FAILED",
        message=(
            f"Agent 运行时发生 {type(error).__name__}；"
            "请在运行记录中查看对应 Turn。"
        ),
        source="system",
    )


def _capability_call_status(
    capability_output: dict[str, Any] | None,
) -> str:
    if capability_output is None:
        return "skipped"
    return str(capability_output.get("status", "completed"))


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
            if turn.workflow_version != WORKFLOW_VERSION:
                turn.status = "failed"
                turn.error = ErrorEnvelope(
                    code="AGENT_CHECKPOINT_VERSION_INCOMPATIBLE",
                    message=(
                        f"checkpoint {turn.workflow_version} cannot resume "
                        f"under workflow {WORKFLOW_VERSION}"
                    ),
                    source="system",
                    retryable=False,
                    details={
                        "checkpoint_workflow_version": turn.workflow_version,
                        "runtime_workflow_version": WORKFLOW_VERSION,
                    },
                ).model_dump(mode="json")
                turn.completed_at = current
                turn.lease_owner = None
                turn.lease_expires_at = None
                continue
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
                "kind": "capability",
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


def _scripted_complex_planning(message: str) -> dict[str, Any] | None:
    """Test-provider script; production never selects this model."""

    requests_synthesis = any(
        term in message for term in ("分析", "总结", "归纳")
    )
    requests_selection = any(
        term in message for term in ("选出", "推荐", "挑选")
    )
    if not (requests_synthesis and requests_selection):
        return None
    hours = 72 if any(
        term in message for term in ("三天", "三日", "3天", "3 天")
    ) else 24
    limit = 3 if any(
        term in message for term in ("三个", "三条", "3条", "3 条")
    ) else 5
    use_existing_only = any(
        term in message for term in ("目前收集", "已有", "现有")
    )
    collect = (
        any(term in message for term in ("收集", "采集"))
        and not use_existing_only
    )
    dependencies: list[str] = []
    steps: list[dict[str, Any]] = []
    if collect:
        steps.append(
            {
                "step_id": "collect",
                "title": "采集热点信息",
                "goal": "采集启用来源；新增为零也继续查询",
                "kind": "capability",
                "domains": ["collection"],
                "capability_id": "collection.run.start",
                "arguments": {},
                "dependencies": [],
                "success_criteria": "采集运行完成",
                "acceptance_policy": {
                    "id": "capability_effect.v1",
                    "params": {},
                },
                "side_effect": "external",
                "risk": "low",
                "failure_policy": "continue_independent",
                "satisfies": [],
            }
        )
        dependencies = ["collect"]
    steps.extend(
        [
            {
                "step_id": "search",
                "title": "统一检索时间窗口",
                "goal": f"跨产品阶段检索最近 {hours} 小时信息",
                "kind": "capability",
                "domains": ["intelligence"],
                "capability_id": "intelligence.search",
                "arguments": {
                    "query": "AI",
                    "scopes": ["intelligence"],
                    "limit": 50,
                },
                "dependencies": dependencies,
                "success_criteria": "返回真实信息 ID",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 1},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "continue_independent",
                "satisfies": [],
            },
            *(
                [
                    {
                        "step_id": "web_search",
                        "title": "按需联网补证",
                        "goal": "仅在本地候选不足时联网搜索并缓存网页",
                        "kind": "capability",
                        "domains": ["collection"],
                        "capability_id": "web.search.collect",
                        "arguments": {
                            "query": "AI 最新动态",
                            "limit": min(max(limit * 2, 6), 20),
                            "freshness": (
                                "pd" if hours <= 24 else "pw"
                            ),
                        },
                        "dependencies": ["search"],
                        "success_criteria": "补证结果已缓存或明确说明跳过原因",
                        "acceptance_policy": {
                            "id": "capability_effect.v1",
                            "params": {},
                        },
                        "side_effect": "external",
                        "risk": "low",
                        "failure_policy": "continue_independent",
                        "satisfies": [],
                    }
                ]
                if collect
                else []
            ),
            {
                "step_id": "recommend",
                "title": "按影响力选出热点",
                "goal": f"使用可解释信号选出最多 {limit} 条",
                "kind": "domain_agent",
                "domains": ["intelligence"],
                "capability_id": "research.recommend",
                "arguments": {
                    "topic": "AI",
                    "lookback_hours": hours,
                    "limit": limit,
                    "rank_by": "impact",
                },
                "dependencies": [
                    "web_search" if collect else "search"
                ],
                "success_criteria": "每条包含来源、理由与站内深链",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 1, "max_items": limit},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "stop_dependents",
                "satisfies": ["recommendations", "evidence"],
            },
            {
                "step_id": "synthesize",
                "title": "综合分析",
                "goal": "基于入选证据形成跨信息分析",
                "kind": "domain_agent",
                "domains": ["intelligence"],
                "capability_id": "research.trend_brief",
                "arguments": {
                    "topic": "AI",
                    "lookback_hours": hours,
                    "limit": limit,
                    "rank_by": "impact",
                    "output_max_chars": 1600,
                },
                "dependencies": ["recommend"],
                "success_criteria": "每个 finding 引用真实信息 ID",
                "acceptance_policy": {
                    "id": "synthesis_grounded.v1",
                    "params": {"min_findings": 1},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "stop_dependents",
                "satisfies": ["trend_summary"],
            },
        ]
    )
    return {
        "goal": {
            "operation_mode": (
                "collect_then_analyze" if collect else "analyze_existing"
            ),
            "topic": "AI",
            "time_window": {"lookback_hours": hours},
            "max_items": limit,
            "ranking_criterion": "impact",
            "deliverables": [
                "recommendations",
                "trend_summary",
                "evidence",
            ],
            "use_existing": True,
            "requires_collection": collect,
            "requires_synthesis": True,
        },
        "plan": {
            "objective": "选出时间范围内高影响力 AI 内容并综合分析",
            "constraints": {
                "lookback_hours": hours,
                "max_items": limit,
                "ranking_criterion": "impact",
            },
            "assumptions": [],
            "planning_mode": "dynamic",
            "selected_domains": (
                ["collection", "intelligence"]
                if collect
                else ["intelligence"]
            ),
            "steps": steps,
            "max_replans": 2,
        },
    }


def _scripted_contextual_planning(
    message: str,
) -> dict[str, Any] | None:
    """Deterministic demo provider coverage, never a production intent router."""

    if not any(term in message for term in ("刚才", "上述", "前面", "这些")):
        return None
    return {
        "goal": {
            "operation_mode": "direct",
            "topic": "AI",
            "time_window": {"lookback_hours": 72},
            "max_items": 3,
            "ranking_criterion": "impact",
            "deliverables": ["model_response"],
            "use_existing": True,
            "requires_collection": False,
            "requires_synthesis": True,
        },
        "plan": {
            "objective": "基于当前会话已有内容回答追问",
            "constraints": {
                "lookback_hours": 72,
                "max_items": 3,
                "ranking_criterion": "impact",
            },
            "assumptions": [
                "只使用有界会话上下文，不把模型常识作为工作区证据"
            ],
            "planning_mode": "direct",
            "selected_domains": [],
            "steps": [
                {
                    "step_id": "reason",
                    "title": "基于会话语境分析",
                    "goal": "直接回答用户对前序内容的分析追问",
                    "kind": "model_reasoning",
                    "domains": [],
                    "capability_id": None,
                    "arguments": {
                        "response_basis": "conversation_context",
                    },
                    "dependencies": [],
                    "success_criteria": "返回有证据边界的自然语言回答",
                    "acceptance_policy": {
                        "id": "contextual_response.v1",
                        "params": {"min_chars": 20},
                    },
                    "side_effect": "read",
                    "risk": "low",
                    "failure_policy": "continue_independent",
                    "satisfies": ["model_response"],
                }
            ],
            "max_replans": 1,
        },
    }


def _scripted_basic_plan(message: str) -> dict[str, Any] | None:
    if any(term in message for term in ("推荐", "选出", "挑选")):
        return None
    if any(
        term in message
        for term in ("每天", "定时", "创建任务", "监测任务")
    ):
        capability_id = "task.draft.propose"
        title = "生成可编辑任务草稿"
        domains = ["tasking"]
        arguments = {"message": message}
        policy = {"id": "capability_effect.v1", "params": {}}
        side_effect = "read"
    elif "审核" in message and any(
        term in message for term in ("保留", "通过", "确认")
    ):
        capability_id = "review.batch.submit"
        title = "确认审核决定"
        domains = ["review"]
        arguments = {"default_decision": "keep", "confirm": True}
        policy = {"id": "capability_effect.v1", "params": {}}
        side_effect = "write"
    elif "卡片" in message and any(
        term in message for term in ("生成", "整理", "制作")
    ):
        capability_id = "poster.draft.generate"
        title = "生成信息卡片"
        domains = ["cards"]
        arguments = {}
        policy = {"id": "capability_effect.v1", "params": {}}
        side_effect = "write"
    elif any(term in message for term in ("采集", "收集", "更新")):
        capability_id = "collection.run.start"
        title = "采集 AI 信息"
        domains = ["collection"]
        arguments: dict[str, Any] = {}
        policy = {"id": "capability_effect.v1", "params": {}}
        side_effect = "external"
    elif any(term in message for term in ("查询时间线", "搜索时间线")):
        capability_id = "intelligence.timeline.query"
        title = "查询 AI 信息"
        domains = ["intelligence"]
        arguments = {"search": "LangGraph", "limit": 50}
        policy = {"id": "information_results.v1", "params": {"min_items": 0}}
        side_effect = "read"
    else:
        return None
    return {
        "objective": title,
        "constraints": {"max_items": 50},
        "assumptions": [],
        "planning_mode": "direct",
        "selected_domains": domains,
        "steps": [
            {
                "step_id": "direct",
                "title": title,
                "goal": title,
                "kind": "capability",
                "domains": domains,
                "capability_id": capability_id,
                "arguments": arguments,
                "dependencies": [],
                "success_criteria": "返回能力结果",
                "acceptance_policy": policy,
                "side_effect": side_effect,
                "risk": "low",
                "failure_policy": "continue_independent",
                "satisfies": ["task_draft"],
            }
        ],
        "max_replans": 0,
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
        system_text = "\n".join(
            str(message.content)
            for message in messages
            if getattr(message, "type", "") == "system"
        )
        if "selected model's own reasoning" in system_text:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content=(
                                "当前可见的会话内容不足以可靠选出三个具体条目。"
                                "我可以基于已出现的条目标题、摘要和来源进行分析，"
                                "但不会把采集数量或运行状态伪装成影响力排名；"
                                "请先提供或保留上一轮的条目级结果。"
                            )
                        )
                    )
                ]
            )
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
                            _scripted_contextual_planning(user_message)
                            or _scripted_complex_planning(user_message)
                            or _scripted_basic_plan(user_message)
                            or _fixture_plan(user_message),
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
    if settings.agent_test_mode:
        return FixturePlannerChatModel(), model.id
    if model.provider == "heuristic":
        if settings.source_seed_mode != "demo":
            raise RuntimeError("AGENT_MODEL_TOOL_CALLING_REQUIRED")
        return FixturePlannerChatModel(), model.id
    if not model.api_key:
        raise RuntimeError("AGENT_MODEL_NOT_CONFIGURED")
    compatibility = resolve_openai_compatibility(model)
    return (
        ChatOpenAI(
            model=model.model_id,
            base_url=model.base_url,
            api_key=SecretStr(model.api_key),
            max_tokens=model.output_token_limit
            or settings.llm_max_output_tokens,
            timeout=settings.llm_timeout_seconds,
            temperature=0,
            extra_body=compatibility.extra_body or None,
            metadata={
                "structured_output_method": (
                    compatibility.structured_output_method
                ),
                "provider_family": compatibility.family,
                "json_object_retry": compatibility.json_object_retry,
            },
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
            current_step_ids = {step.step_id for step in plan.steps}
            previous_steps = list(
                self.session.scalars(
                    select(AgentTurnStepModel).where(
                        AgentTurnStepModel.turn_id == self.turn.id
                    )
                )
            )
            for previous in previous_steps:
                if (
                    previous.step_id not in current_step_ids
                    and previous.status in {"pending", "running"}
                ):
                    previous.status = "superseded"
                    previous.completed_at = now
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
        elif event_type in {
            "tool.completed",
            "model.reasoning.completed",
            "step.outcome",
        }:
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
            workflow_version=WORKFLOW_VERSION,
            manifest=ExecutionManifest(
                model_config_ref=payload.model_id or "workspace-default",
                requested_model_id=payload.model_id,
                capability_snapshot_digest=digest,
                artifact_ids=payload.artifact_ids,
            ).model_dump(mode="json"),
        )
        user_message = AgentMessageModel(
            conversation_id=conversation_id,
            role="user",
            content=payload.message,
            client_message_id=payload.client_message_id,
            request_id=request_id,
            turn_id=turn.id,
            requested_model_id=payload.model_id,
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

    def complete_direct_response(
        self,
        turn_id: str,
        *,
        model_service: ModelConfigurationService,
        model_chat: Any,
        model_id: str | None,
        image_urls: list[str],
    ) -> AgentTurnRead:
        """Complete a model-only request inside the canonical Turn lifecycle."""

        turn = self.session.get(AgentTurnModel, turn_id)
        if turn is None:
            raise LookupError("AGENT_TURN_NOT_FOUND")
        if turn.status in TERMINAL_STATUSES:
            return AgentTurnRead.model_validate(turn)
        started_at = datetime.now(timezone.utc)
        turn.status = "running"
        turn.started_at = started_at
        journal = EventJournal(self.session, turn)
        plan = AgentPlan(
            objective="直接回复用户消息",
            constraints={"image_count": len(image_urls)},
            planning_mode="direct",
            selected_domains=["agent"],
            steps=[
                PlanStep(
                    step_id="direct",
                    title="生成直接回复",
                    goal="使用用户选择的模型生成回复",
                    kind="domain_agent",
                    domains=["agent"],
                    capability_id="agent.message.complete",
                    success_criteria="返回可展示的模型回复",
                    acceptance_policy=AcceptancePolicy(
                        id="capability_effect.v1"
                    ),
                    side_effect="read",
                    satisfies=["direct_response"],
                )
            ],
            max_replans=0,
        )
        goal = AgentGoalSpec(
            operation_mode="direct",
            time_window=GoalTimeWindow(lookback_hours=1),
            max_items=1,
            ranking_criterion="relevance",
            deliverables=["direct_response"],
        )
        journal.append(
            "plan.ready",
            {"goal": goal.model_dump(mode="json"), "plan": plan.model_dump(mode="json")},
        )
        effective_model_id: str | None = None
        error: ModelConfigurationError | None = None
        try:
            selection = model_service.select_for_request(model_id)
            effective_model_id = selection.effective_model.id
            if image_urls and not selection.effective_model.supports_vision:
                raise ModelConfigurationError("MODEL-002")
            message = model_chat.complete(
                selection.effective_model,
                turn.message,
                image_urls,
            )
        except ModelConfigurationError as caught:
            error = caught
            message = str(caught)

        completed_at = datetime.now(timezone.utc)
        duration_ms = max(
            0,
            int((completed_at - started_at).total_seconds() * 1000),
        )
        capability_output = (
            {
                "status": "failed",
                "error_code": error.code,
            }
            if error is not None
            else {
                "status": "completed",
                "model_id": effective_model_id,
            }
        )
        result = AgentTurnResult(
            status="failed" if error is not None else "complete",
            message=message,
            goal=goal,
            plan=plan,
            result_blocks=[
                AgentResultBlock(
                    block_id=new_id("block"),
                    type="plan_summary",
                    title="直接回复",
                    data={
                        "mode": "direct",
                        "image_count": len(image_urls),
                        "model_id": effective_model_id,
                    },
                )
            ],
            capability_results={"direct": capability_output},
            errors=(
                [
                    ErrorEnvelope(
                        code=error.code,
                        message=str(error),
                        source="provider",
                    )
                ]
                if error is not None
                else []
            ),
            total_duration_ms=duration_ms,
        )
        manifest = dict(turn.manifest)
        manifest["effective_model_id"] = effective_model_id
        turn.manifest = manifest
        turn.status = result.status
        turn.plan = plan.model_dump(mode="json")
        turn.result = result.model_dump(mode="json")
        turn.error = (
            result.errors[0].model_dump(mode="json")
            if result.errors
            else None
        )
        turn.completed_at = completed_at
        turn.total_duration_ms = duration_ms
        self.session.add(
            AgentMessageModel(
                conversation_id=turn.conversation_id,
                role="assistant",
                content=message,
                request_id=turn.request_id,
                turn_id=turn.id,
                result_data=result.model_dump(mode="json"),
                error_code=error.code if error is not None else None,
                effective_model_id=effective_model_id,
                image_count=len(image_urls),
            )
        )
        user_message = self.session.scalar(
            select(AgentMessageModel).where(
                AgentMessageModel.turn_id == turn.id,
                AgentMessageModel.role == "user",
            )
        )
        if user_message is not None:
            user_message.image_count = len(image_urls)
        conversation = self.session.get(
            AgentConversationModel,
            turn.conversation_id,
        )
        if conversation is not None:
            conversation.active_turn_id = None
            conversation.last_message_at = completed_at
            conversation.updated_at = completed_at
        self.session.commit()
        journal.append(
            "result.block",
            result.result_blocks[0].model_dump(mode="json"),
        )
        journal.append(
            "turn.failed" if error is not None else "turn.completed",
            {"status": result.status, "total_duration_ms": duration_ms},
        )
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
        effective_model_id: str | None = None
        try:
            executor = build_capability_executor(session, settings)
            planner_model, effective_model_id = build_planner_model(
                settings,
                model_service,
                model_id,
            )
            manifest = dict(turn.manifest)
            manifest["effective_model_id"] = effective_model_id
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
            try:
                customization = AgentPackService(
                    session,
                    settings.agent_pack_root,
                ).get_customization("ai-editor")
            except (AgentPackError, LookupError, OSError, UnicodeError) as error:
                customization = {
                    "version": "built-in-defaults",
                    "rules": DEFAULT_RULES,
                    "skills": DEFAULT_SKILLS,
                }
                journal.append(
                    "context.customization.fallback",
                    {
                        "status": "degraded",
                        "error_code": "AGENT_PACK_UNAVAILABLE",
                        "error_type": type(error).__name__,
                    },
                )
            manifest["agent_pack_version"] = customization["version"]
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
                workspace_rules=str(customization["rules"]),
                workspace_skills=list(customization["skills"]),
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
                    conversation_context=_bounded_conversation_context(
                        session,
                        turn,
                    ),
                    effective_model_id=effective_model_id,
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
            provider_error = next(
                (
                    item
                    for item in result.errors
                    if item.source == "provider"
                ),
                None,
            )
            if provider_error is not None and effective_model_id:
                model_service.mark_needs_retest(
                    effective_model_id,
                    provider_error.code,
                )
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
                        "status": _capability_call_status(
                            result.capability_results.get(step.step_id)
                        ),
                    }
                    for step in result.plan.steps
                    if step.capability_id is not None
                ]
            assistant.result_data = result.model_dump(mode="json")
            task_proposal = next(
                (
                    output
                    for step_id, output in result.capability_results.items()
                    if any(
                        step.step_id == step_id
                        and step.capability_id == "task.draft.propose"
                        for step in result.plan.steps
                    )
                ),
                None,
            )
            if task_proposal is not None:
                assistant.schedule_draft = task_proposal.get(
                    "schedule_draft"
                )
                assistant.task_draft = task_proposal.get("task_draft")
            capability_error_code = next(
                (
                    str(error_item["error_code"])
                    for output in result.capability_results.values()
                    for error_item in output.get("errors", [])
                    if error_item.get("error_code")
                ),
                None,
            )
            assistant.error_code = capability_error_code or (
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
            envelope = _execution_error_envelope(error)
            if envelope.source == "provider" and effective_model_id:
                model_service.mark_needs_retest(
                    effective_model_id,
                    envelope.code,
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
                    content=f"{envelope.code}（{envelope.message}）",
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


def _bounded_conversation_context(
    session: Session,
    turn: AgentTurnModel,
) -> dict[str, Any]:
    messages = list(
        session.scalars(
            select(AgentMessageModel)
            .where(
                AgentMessageModel.conversation_id == turn.conversation_id,
                AgentMessageModel.id
                != session.scalar(
                    select(AgentMessageModel.id).where(
                        AgentMessageModel.turn_id == turn.id,
                        AgentMessageModel.role == "user",
                    )
                ),
            )
            .order_by(AgentMessageModel.created_at.desc())
            .limit(8)
        )
    )
    messages.reverse()
    previous_turns = list(
        session.scalars(
            select(AgentTurnModel)
            .where(
                AgentTurnModel.conversation_id == turn.conversation_id,
                AgentTurnModel.id != turn.id,
            )
            .order_by(AgentTurnModel.created_at.desc())
            .limit(3)
        )
    )
    return {
        "conversation_id": turn.conversation_id,
        "recent_messages": [
            {
                "role": message.role,
                "summary": " ".join(message.content.split())[:500],
                "turn_id": message.turn_id,
            }
            for message in messages
        ],
        "prior_turn_refs": [
            {
                "turn_id": previous.id,
                "workflow_version": previous.workflow_version,
                "status": previous.status,
                "goal": previous.result.get("goal"),
                "business_run_ids": previous.result.get(
                    "business_run_ids",
                    [],
                ),
                "result_block_ids": [
                    block.get("block_id")
                    for block in previous.result.get("result_blocks", [])[:8]
                ],
                "result_summaries": [
                    _bounded_result_block(block)
                    for block in previous.result.get("result_blocks", [])[:8]
                    if block.get("type")
                    in {
                        "signal_preview",
                        "recommendation_list",
                        "trend_summary",
                        "model_response",
                        "collection_summary",
                    }
                ][:6],
            }
            for previous in previous_turns
        ],
    }


def _bounded_result_block(block: dict[str, Any]) -> dict[str, Any]:
    """Retain small answer-bearing fields, never full pages or raw tool JSON."""

    block_type = str(block.get("type", ""))
    data = block.get("data")
    data = data if isinstance(data, dict) else {}
    if block_type == "signal_preview":
        bounded_data = {
            key: data.get(key)
            for key in (
                "information_id",
                "title",
                "source_name",
                "published_at",
                "color",
                "quick_summary",
                "ranking_basis",
                "app_path",
            )
            if data.get(key) is not None
        }
    elif block_type == "recommendation_list":
        bounded_data = {
            "items": [
                {
                    key: item.get(key)
                    for key in (
                        "information_id",
                        "title",
                        "source_name",
                        "published_at",
                        "color",
                        "summary",
                        "ranking_basis",
                        "app_path",
                    )
                    if item.get(key) is not None
                }
                for item in data.get("items", [])[:3]
                if isinstance(item, dict)
            ]
        }
    elif block_type == "trend_summary":
        bounded_data = {
            "overview": str(data.get("overview", ""))[:1000],
            "key_findings": data.get("key_findings", [])[:5],
            "uncertainties": data.get("uncertainties", [])[:5],
        }
    elif block_type == "model_response":
        bounded_data = {
            "content": str(data.get("content", ""))[:1600],
            "basis": data.get("basis"),
            "information_ids": data.get("information_ids", [])[:20],
        }
    else:
        bounded_data = {
            key: data.get(key)
            for key in (
                "run_id",
                "status",
                "items_collected",
                "items_added",
            )
            if data.get(key) is not None
        }
    return {
        "block_id": block.get("block_id"),
        "type": block_type,
        "title": str(block.get("title", ""))[:240],
        "data": bounded_data,
    }
