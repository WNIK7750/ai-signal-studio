from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import Field

from ai_signal_api.agent_runtime.context import (
    ContextAssembler,
    build_working_memory,
    serialize_bounded_json,
)
from ai_signal_api.agent_runtime.contracts import (
    ActionEnvelope,
    AgentGoalSpec,
    AgentPlan,
    AgentPlanningOutput,
    AgentResultBlock,
    AgentTurnResult,
    ErrorEnvelope,
    GoalTimeWindow,
    ModelReasoningOutput,
    validate_goal_plan_coverage,
)
from ai_signal_api.agent_runtime.tools import (
    PLANNING_CAPABILITY_CONTRACTS,
    TOOL_SCHEMAS,
    build_capability_tool,
)
from ai_signal_api.capabilities.core import (
    CapabilityExecutionError,
    CapabilityExecutor,
)
from ai_signal_api.modules.intelligence.agent.schemas import (
    ResearchAnalysisSynthesis,
    ResearchInput,
    TrendSynthesis,
)
from ai_signal_api.modules.intelligence.search import IntelligenceSearchInput
from ai_signal_api.modules.collection.web_discovery import (
    WebSearchCollectInput,
)
from ai_signal_api.schemas import (
    CollectionRunStart,
    ExecutionContext,
    TimelineQuery,
)


EventSink = Callable[[str, dict[str, Any], str | None], None]


class AgentTaskState(TypedDict, total=False):
    turn_id: str
    conversation_id: str
    request_id: str
    message: str
    goal: dict[str, Any]
    conversation_context: dict[str, Any]
    effective_model_id: str
    plan: dict[str, Any]
    active_step_index: int
    active_step: dict[str, Any] | None
    action: dict[str, Any] | None
    step_outputs: dict[str, dict[str, Any]]
    errors: list[dict[str, Any]]
    status: str
    result: dict[str, Any]
    selected_domain_ids: list[str]
    loaded_tool_ids: list[str]
    business_run_ids: list[str]
    cancel_requested: bool
    retry_count: int
    retry_source_ids: list[str]
    clarification_answer: str
    approval_granted: bool
    approval_rejected: bool
    step_statuses: dict[str, str]
    replan_count: int
    replan_requested: bool
    research_analysis_failed: bool


class BoundActionChatModel(BaseChatModel):
    """A bounded LangChain model that can call exactly one validated tool."""

    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "bounded-action-binder"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        if any(isinstance(message, ToolMessage) for message in messages):
            message = AIMessage(content="Validated capability completed.")
        else:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": self.tool_name,
                        "args": self.tool_input,
                        "id": "bounded_action",
                        "type": "tool_call",
                    }
                ],
            )
        return ChatResult(generations=[ChatGeneration(message=message)])


class WorkspaceGraphRunner:
    """The executable 0.8.0 graph for bounded, goal-covered turns."""

    def __init__(
        self,
        *,
        executor: CapabilityExecutor,
        planner_model: BaseChatModel,
        synthesis_model: BaseChatModel | None = None,
        checkpointer: BaseCheckpointSaver,
        event_sink: EventSink | None = None,
        cancellation_checker: Callable[[str], bool] | None = None,
        workspace_rules: str = "",
        workspace_skills: list[dict[str, Any]] | None = None,
    ) -> None:
        self.executor = executor
        self.planner_model = planner_model
        self.synthesis_model = synthesis_model or planner_model
        self.context = ContextAssembler(
            executor,
            workspace_rules=workspace_rules,
            workspace_skills=workspace_skills,
        )
        self.event_sink = event_sink or (lambda *_args: None)
        self.cancellation_checker = cancellation_checker or (
            lambda _turn_id: False
        )
        self.graph = self._build().compile(checkpointer=checkpointer)

    def run(
        self,
        *,
        turn_id: str,
        conversation_id: str,
        request_id: str,
        message: str,
        cancel_requested: bool = False,
        retry_count: int = 0,
        retry_source_ids: list[str] | None = None,
        conversation_context: dict[str, Any] | None = None,
        effective_model_id: str = "workspace-default",
    ) -> AgentTurnResult:
        final = self.advance(
            turn_id=turn_id,
            conversation_id=conversation_id,
            request_id=request_id,
            message=message,
            cancel_requested=cancel_requested,
            retry_count=retry_count,
            retry_source_ids=retry_source_ids,
            conversation_context=conversation_context,
            effective_model_id=effective_model_id,
        )
        if "__interrupt__" in final:
            raise RuntimeError("AGENT_TURN_WAITING_FOR_RESUME")
        return AgentTurnResult.model_validate(final["result"])

    def advance(
        self,
        *,
        turn_id: str,
        conversation_id: str,
        request_id: str,
        message: str,
        cancel_requested: bool = False,
        retry_count: int = 0,
        retry_source_ids: list[str] | None = None,
        conversation_context: dict[str, Any] | None = None,
        effective_model_id: str = "workspace-default",
    ) -> dict[str, Any]:
        state = self.graph.invoke(
            {
                "turn_id": turn_id,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "message": message,
                "conversation_context": conversation_context or {},
                "effective_model_id": effective_model_id,
                "active_step_index": 0,
                "step_outputs": {},
                "errors": [],
                "status": "running",
                "business_run_ids": [],
                "cancel_requested": cancel_requested,
                "retry_count": retry_count,
                "retry_source_ids": retry_source_ids or [],
                "step_statuses": {},
                "replan_count": 0,
            },
            config={"configurable": {"thread_id": turn_id}},
        )
        return self._waiting_projection(state)

    def resume(
        self,
        *,
        turn_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        state = self.graph.invoke(
            Command(resume=payload),
            config={"configurable": {"thread_id": turn_id}},
        )
        return self._waiting_projection(state)

    @staticmethod
    def _waiting_projection(state: dict[str, Any]) -> dict[str, Any]:
        interrupts = state.get("__interrupt__", ())
        if not interrupts:
            return state
        value = interrupts[0].value
        kind = str(value.get("kind", "clarification"))
        return {
            **state,
            "status": (
                "waiting_approval"
                if kind == "approval"
                else "waiting_input"
            ),
            "interrupt": value,
        }

    def _build(self) -> StateGraph:
        builder = StateGraph(AgentTaskState)
        nodes = {
            "N01": self._accept_turn,
            "N02": self._supervise_run,
            "N03": self._normalize_input,
            "N04": self._bootstrap_context,
            "N05": self._route_complexity,
            "N06": self._build_fast_plan,
            "N07": self._build_structured_plan,
            "N08": self._validate_plan,
            "N09": self._clarification_placeholder,
            "N10": self._schedule_ready_step,
            "N11": self._assemble_step_context,
            "N12": self._bind_action,
            "N13": self._validate_action,
            "N14": self._capability_gate,
            "N15": self._approval_placeholder,
            "N16": self._route_executor,
            "N17": self._execute_capability,
            "N18": self._execute_domain_agent,
            "N19": self._execute_domain_workflow,
            "N20": self._record_result,
            "N21": self._join_results,
            "N22": self._inspect_outcome,
            "N23": self._control_failure,
            "N24": self._compose_result,
            "N25": self._finalize,
        }
        for node_id, node in nodes.items():
            builder.add_node(node_id, node)
        builder.add_edge(START, "N01")
        builder.add_edge("N01", "N02")
        builder.add_edge("N02", "N03")
        builder.add_edge("N03", "N04")
        builder.add_edge("N04", "N05")
        builder.add_conditional_edges(
            "N05",
            lambda state: "N06"
            if state.get("plan", {}).get("planning_mode") == "fast"
            else "N07",
        )
        builder.add_edge("N06", "N08")
        builder.add_edge("N07", "N08")
        builder.add_conditional_edges(
            "N08",
            lambda state: (
                "N23"
                if state.get("status") == "failed"
                else "N09"
                if state.get("plan", {})
                .get("constraints", {})
                .get("requires_clarification")
                and not state.get("clarification_answer")
                else "N10"
            ),
        )
        builder.add_edge("N09", "N10")
        builder.add_conditional_edges(
            "N10",
            lambda state: (
                "N24"
                if state.get("cancel_requested")
                or state.get("active_step") is None
                else "N11"
            ),
        )
        builder.add_edge("N11", "N12")
        builder.add_edge("N12", "N13")
        builder.add_conditional_edges(
            "N13",
            lambda state: "N14"
            if state.get("status") != "failed"
            else "N23",
        )
        builder.add_conditional_edges(
            "N14",
            lambda state: (
                "N23"
                if state.get("status") == "failed"
                else "N15"
                if state.get("status") == "waiting_approval"
                else "N16"
            ),
        )
        builder.add_conditional_edges(
            "N16",
            lambda state: (
                "N18"
                if state["active_step"]["kind"]
                in {"domain_agent", "model_reasoning"}
                else "N19"
                if state["active_step"]["kind"] == "domain_workflow"
                else "N17"
            ),
        )
        builder.add_conditional_edges(
            "N15",
            lambda state: "N20"
            if state.get("approval_rejected")
            else "N12",
        )
        builder.add_edge("N17", "N20")
        builder.add_edge("N18", "N20")
        builder.add_edge("N19", "N20")
        builder.add_edge("N20", "N21")
        builder.add_edge("N21", "N22")
        builder.add_conditional_edges(
            "N22",
            lambda state: (
                "N23"
                if state.get("status") == "failed"
                else "N24"
                if state.get("active_step_index", 0)
                >= len(state.get("plan", {}).get("steps", []))
                else "N10"
            ),
        )
        builder.add_conditional_edges(
            "N23",
            lambda state: "N07"
            if state.get("replan_requested")
            else "N24",
        )
        builder.add_edge("N24", "N25")
        builder.add_edge("N25", END)
        return builder

    def _accept_turn(self, state: AgentTaskState) -> dict[str, Any]:
        return {"status": "running"}

    def _supervise_run(self, state: AgentTaskState) -> dict[str, Any]:
        if self._cancelled(state):
            return {"status": "cancelled", "cancel_requested": True}
        return {}

    def _normalize_input(self, state: AgentTaskState) -> dict[str, Any]:
        return {"message": " ".join(state["message"].split())}

    def _bootstrap_context(self, state: AgentTaskState) -> dict[str, Any]:
        return {
            "selected_domain_ids": [],
            "loaded_tool_ids": [],
        }

    def _build_fast_plan(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _route_complexity(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _build_structured_plan(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        base = self.context.assemble(
            selected_domain_ids=[],
            message=state["message"],
            step=None,
            evidence=[],
        )
        prior_context = self._serialize_model_payload(
            state,
            state.get("conversation_context", {}),
            max_chars=4000,
            layer="conversation_context",
        )
        prior_has_answering_content = any(
            reference.get("result_summaries")
            for reference in state.get(
                "conversation_context",
                {},
            ).get("prior_turn_refs", [])
        )
        replan_feedback = [
            item
            for item in state.get("errors", [])
            if item.get("code") in {
                "AGENT_PLAN_INVALID",
                "AGENT_PLAN_COVERAGE_INCOMPLETE",
                "AGENT_OUTCOME_REJECTED",
            }
        ]
        messages = [
            SystemMessage(
                content=(
                    f"{base.system_prompt}\n\n"
                    "可选 Domain Index：collection（采集），"
                    "intelligence（查询、推荐与综合分析）。"
                    "工具是获取工作区事实、实时证据和执行动作的优先手段，"
                    "但不是每个步骤的必选项。解释、比较、归纳、基于当前"
                    "会话语境的回答，可以规划 kind=model_reasoning；该种"
                    "步骤 capability_id 必须为 null、side_effect=read、"
                    "acceptance_policy.id=contextual_response.v1。"
                    "model_reasoning 必须使用本轮 effective model，"
                    "只能根据有界会话上下文与前序步骤输出推理，并明确"
                    "证据边界，不得虚构工作区 ID、实时数据或工具结果。"
                    "如果用户要求工作区最新数据、可验证信息或业务动作，"
                    "再使用以下精确 capability_id，禁止翻译、缩写或发明："
                    "collection.run.start、"
                    "intelligence.search、web.search.collect、"
                    "research.recommend、research.trend_brief。"
                    "用户显式要求重新查询工作区时间范围时，"
                    "collect_then_analyze 必须按上述五个 ID 顺序形成依赖链；"
                    "其中 web.search.collect 会在本地候选充足时自动跳过，"
                    "不得由模型臆测是否有足够证据。"
                    "analyze_existing 不得采集或联网，使用"
                    "intelligence.search→research.recommend"
                    "→research.trend_brief。"
                    "统一检索 arguments 使用 query、scopes、limit；"
                    "联网补证 arguments 使用 query、limit、freshness；"
                    "推荐与综合 arguments 使用 topic、lookback_hours、"
                    "limit、rank_by。"
                    "以下 Planning Contract 的 domain、kind、side_effect、risk 与 "
                    "acceptance_policy 必须逐项完全一致；这些字段由服务端"
                    "能力契约最终裁定，模型不得提升或降低审批级别："
                    f"{json.dumps(PLANNING_CAPABILITY_CONTRACTS, ensure_ascii=False)}。"
                    "用户要求三个时 max_items 与 limit 必须为 3。"
                    "研究工具链 deliverables 使用 recommendations、"
                    "trend_summary、evidence；纯语境回答使用 model_response。"
                    "必须先返回结构化 Goal，再返回覆盖全部 deliverables 的 Plan。"
                    "计划中每个 deliverable 必须由步骤 satisfies 声明。"
                    "返回符合 AgentPlanningOutput Schema 的单一 json object。"
                    f"\n有界会话上下文：{prior_context}"
                    "\n最高优先的语境规则：当当前请求是对前序回答或"
                    "刚才收集内容的归纳、挑选、解释或总结，并且"
                    f"context_has_answering_content={str(prior_has_answering_content).lower()}，"
                    "必须使用 operation_mode=direct、deliverables=[model_response]，"
                    "并只规划一个 kind=model_reasoning 的步骤；不得再次查询、"
                    "推荐或调用 trend_brief。若上下文只有运行元数据而没有"
                    "条目正文，仍用 model_reasoning 明确说明证据不足，"
                    "不得虚构三个条目。只有用户明确要求新的工作区时间范围、"
                    "最新事实或执行动作时，才选择工具链。"
                    "\n最终优先级覆盖规则，严格按三类判断："
                    "（1）当前请求明确要求收集或采集，并给出时间范围时，"
                    "使用 collect_then_analyze 和 collect→search→web_search"
                    "→recommend"
                    "→trend_brief；"
                    "（2）当前请求给出新的时间范围但没有要求收集或采集时，"
                    "即使提到“目前收集/已有内容”，也使用 analyze_existing "
                    "和 search→recommend→trend_brief；"
                    "（3）当前请求没有新的时间范围，只指代刚才/上述内容时，"
                    "使用 direct/model_reasoning。不得把第（1）类漏掉 collect，"
                    "也不得把第（2）类变成 direct。"
                    f"\n上次校验反馈：{json.dumps(replan_feedback[-1:], ensure_ascii=False)}"
                )
            ),
            HumanMessage(content=state["message"]),
        ]
        try:
            metadata = getattr(self.planner_model, "metadata", None) or {}
            if isinstance(self.planner_model, ChatOpenAI):
                structured = self.planner_model.with_structured_output(
                    AgentPlanningOutput,
                    method=str(
                        metadata.get(
                            "structured_output_method",
                            "function_calling",
                        )
                    ),
                    include_raw=True,
                )
                planning = None
                parsing_error: Exception | None = None
                attempt_messages = list(messages)
                for _attempt in range(2):
                    envelope = structured.invoke(attempt_messages)
                    if not isinstance(envelope, dict):
                        raise ValueError("AGENT_PLAN_ENVELOPE_INVALID")
                    parsed = envelope.get("parsed")
                    if parsed is not None:
                        planning = (
                            parsed
                            if isinstance(parsed, AgentPlanningOutput)
                            else AgentPlanningOutput.model_validate(parsed)
                        )
                        break
                    try:
                        planning = AgentPlanningOutput.model_validate(
                            self._decode_structured_raw(
                                envelope.get("raw")
                            )
                        )
                        break
                    except Exception as raw_error:
                        parsing_error = (
                            envelope.get("parsing_error") or raw_error
                        )
                    attempt_messages = [
                        *messages,
                        HumanMessage(
                            content=(
                                "上一份结构化计划未通过 Schema 校验。"
                                "必须保留全部必填字段并严格按 Schema 重做；"
                                "不要返回简化结构。校验错误："
                                f"{str(parsing_error)[:3000]}"
                            )
                        ),
                    ]
                if planning is None:
                    raise ValueError(
                        "AGENT_PLAN_RESPONSE_INVALID:"
                        f"{str(parsing_error)[:1000]}"
                    )
            else:
                structured = self.planner_model.with_structured_output(
                    AgentPlanningOutput
                )
                planning_value = structured.invoke(messages)
                planning = (
                    planning_value
                    if isinstance(planning_value, AgentPlanningOutput)
                    else AgentPlanningOutput.model_validate(planning_value)
                )
        except (NotImplementedError, AttributeError, ValueError, TypeError):
            if isinstance(self.planner_model, ChatOpenAI):
                raise
            response = self.planner_model.invoke(messages)
            content = response.content
            if not isinstance(content, str):
                raise ValueError("AGENT_PLAN_RESPONSE_INVALID")
            decoded = json.loads(content)
            if "goal" in decoded and "plan" in decoded:
                planning = AgentPlanningOutput.model_validate(decoded)
            else:
                plan = self._upgrade_legacy_plan(
                    AgentPlan.model_validate(decoded)
                )
                planning = AgentPlanningOutput(
                    goal=self._legacy_goal(plan),
                    plan=plan,
                )
        plan = self._apply_server_planning_contracts(
            planning.plan,
            planning.goal,
        )
        self.event_sink(
            "plan.ready",
            {
                "goal": planning.goal.model_dump(mode="json"),
                "plan": plan.model_dump(mode="json"),
                "planning_mode": plan.planning_mode,
                "effective_model_id": state.get("effective_model_id"),
            },
            None,
        )
        return {
            "plan": plan.model_dump(mode="json"),
            "goal": planning.goal.model_dump(mode="json"),
            "selected_domain_ids": plan.selected_domains,
        }

    @staticmethod
    def _apply_server_planning_contracts(
        plan: AgentPlan,
        goal: AgentGoalSpec,
    ) -> AgentPlan:
        """Replace model-authored execution metadata with server contracts."""

        normalized_steps = []
        for step in plan.steps:
            contract = PLANNING_CAPABILITY_CONTRACTS.get(
                step.capability_id
            )
            if contract is None:
                normalized_steps.append(
                    step.model_copy(update={"domains": []})
                    if step.kind == "model_reasoning"
                    else step
                )
                continue
            arguments = dict(step.arguments)
            if step.capability_id in {
                "research.recommend",
                "research.trend_brief",
            }:
                arguments.update(
                    {
                        "lookback_hours": (
                            goal.time_window.lookback_hours
                        ),
                        "limit": goal.max_items,
                        "rank_by": goal.ranking_criterion,
                    }
                )
            normalized_steps.append(
                step.model_copy(
                    update={
                        "kind": contract["kind"],
                        "domains": [contract["domain"]],
                        "side_effect": contract["side_effect"],
                        "risk": contract["risk"],
                        "acceptance_policy": (
                            step.acceptance_policy.model_copy(
                                update={
                                    "id": contract[
                                        "acceptance_policy"
                                    ]
                                }
                            )
                        ),
                        "arguments": arguments,
                    }
                )
            )
        constraints = dict(plan.constraints)
        constraints.update(
            {
                "lookback_hours": goal.time_window.lookback_hours,
                "max_items": goal.max_items,
                "ranking_criterion": goal.ranking_criterion,
            }
        )
        selected_domains = list(
            dict.fromkeys(
                domain_id
                for step in normalized_steps
                for domain_id in step.domains
            )
        )
        return plan.model_copy(
            update={
                "steps": normalized_steps,
                "constraints": constraints,
                "selected_domains": selected_domains,
            }
        )

    @staticmethod
    def _upgrade_legacy_plan(plan: AgentPlan) -> AgentPlan:
        steps = []
        for step in plan.steps:
            if step.satisfies:
                steps.append(step)
                continue
            satisfies: list[str] = []
            if step.capability_id in {
                "intelligence.recommend",
                "research.recommend",
            }:
                satisfies.append("recommendations")
            if step.capability_id in {
                "intelligence.timeline.query",
                "intelligence.search",
            }:
                satisfies.append("evidence")
            if step.capability_id == "research.trend_brief":
                satisfies.extend(["trend_summary", "evidence"])
            elif (
                step.capability_id is not None
                and step.capability_id.startswith("research.")
            ):
                satisfies.append("evidence")
            if not satisfies:
                satisfies.append("execution_result")
            steps.append(step.model_copy(update={"satisfies": satisfies}))
        return plan.model_copy(update={"steps": steps})

    @staticmethod
    def _legacy_goal(plan: AgentPlan) -> AgentGoalSpec:
        capabilities = {step.capability_id for step in plan.steps}
        deliverables = list(
            dict.fromkeys(
                deliverable
                for step in plan.steps
                for deliverable in step.satisfies
            )
        )
        hours = int(plan.constraints.get("lookback_hours", 24 * 30))
        max_items = min(20, int(plan.constraints.get("max_items", 5)))
        synthesis = "research.trend_brief" in capabilities
        return AgentGoalSpec(
            operation_mode="execute",
            topic=str(plan.constraints.get("topic", "AI")),
            time_window=GoalTimeWindow(lookback_hours=hours),
            max_items=max_items,
            ranking_criterion=str(
                plan.constraints.get("ranking_criterion", "impact")
            ),
            deliverables=deliverables,
            use_existing=True,
            requires_collection="collection.run.start" in capabilities,
            requires_synthesis=synthesis,
        )

    def _validate_plan(self, state: AgentTaskState) -> dict[str, Any]:
        try:
            plan = AgentPlan.model_validate(state["plan"])
            allowed = set(self.executor.registry.ids())
            if any(
                step.kind != "model_reasoning"
                and step.capability_id not in allowed
                for step in plan.steps
            ):
                raise ValueError("AGENT_PLAN_CAPABILITY_UNKNOWN")
            goal = AgentGoalSpec.model_validate(state["goal"])
            gaps = validate_goal_plan_coverage(goal, plan)
            for step in plan.steps:
                contract = PLANNING_CAPABILITY_CONTRACTS.get(
                    step.capability_id
                )
                if contract is None:
                    continue
                for field, actual in (
                    ("kind", step.kind),
                    ("side_effect", step.side_effect),
                    ("risk", step.risk),
                    (
                        "acceptance_policy",
                        step.acceptance_policy.id,
                    ),
                ):
                    expected = contract[field]
                    if actual != expected:
                        gaps.append(
                            "capability_contract_mismatch:"
                            f"{step.capability_id}:{field}:"
                            f"{actual}!={expected}"
                        )
            if gaps:
                errors = list(state.get("errors", []))
                errors.append(
                    ErrorEnvelope(
                        code="AGENT_PLAN_COVERAGE_INCOMPLETE",
                        message=";".join(gaps),
                        source="input",
                        retryable=True,
                        details={"gaps": gaps},
                    ).model_dump(mode="json")
                )
                return {
                    "status": "failed",
                    "errors": errors,
                }
            by_id = {step.step_id: step for step in plan.steps}
            ordered = []
            remaining = set(by_id)
            while remaining:
                ready = [
                    step
                    for step in plan.steps
                    if step.step_id in remaining
                    and all(
                        dependency not in remaining
                        for dependency in step.dependencies
                    )
                ]
                if not ready:
                    raise ValueError("AGENT_PLAN_DEPENDENCY_CYCLE")
                ordered.extend(ready)
                remaining.difference_update(
                    step.step_id for step in ready
                )
            normalized = plan.model_copy(update={"steps": ordered})
            return {
                "plan": normalized.model_dump(mode="json"),
                "errors": [
                    error
                    for error in state.get("errors", [])
                    if error.get("code")
                    != "AGENT_PLAN_COVERAGE_INCOMPLETE"
                ],
                "step_statuses": {
                    step.step_id: "pending" for step in normalized.steps
                },
                "replan_requested": False,
                "status": "running",
            }
        except Exception as error:
            return {
                "status": "failed",
                "errors": [
                    ErrorEnvelope(
                        code="AGENT_PLAN_INVALID",
                        message=str(error),
                        source="input",
                    ).model_dump(mode="json")
                ],
            }

    def _clarification_placeholder(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        payload = interrupt(
            {
                "kind": "clarification",
                "question": state["plan"]
                .get("constraints", {})
                .get("clarification_question", "请补充执行所需信息。"),
                "turn_id": state["turn_id"],
            }
        )
        answer = str(payload.get("answer", "")).strip()
        if not answer:
            return {
                "status": "failed",
                "errors": [
                    ErrorEnvelope(
                        code="CLARIFICATION_REQUIRED",
                        message="补充内容不能为空。",
                        source="input",
                    ).model_dump(mode="json")
                ],
            }
        plan = dict(state["plan"])
        constraints = dict(plan.get("constraints", {}))
        constraints["requires_clarification"] = False
        constraints["clarification_answer"] = answer
        plan["constraints"] = constraints
        return {
            "status": "running",
            "clarification_answer": answer,
            "plan": plan,
        }

    def _schedule_ready_step(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        if self._cancelled(state):
            return {"status": "cancelled", "active_step": None}
        steps = state["plan"]["steps"]
        index = state.get("active_step_index", 0)
        statuses = dict(state.get("step_statuses", {}))
        while index < len(steps):
            step = steps[index]
            dependency_statuses = [
                statuses.get(dependency, "pending")
                for dependency in step.get("dependencies", [])
            ]
            if any(
                value in {"failed", "skipped_dependency", "cancelled"}
                for value in dependency_statuses
            ):
                statuses[step["step_id"]] = "skipped_dependency"
                self.event_sink(
                    "step.skipped",
                    {
                        "step": step,
                        "reason": "dependency_failed",
                    },
                    step["step_id"],
                )
                index += 1
                continue
            break
        if index >= len(steps):
            return {
                "active_step": None,
                "active_step_index": index,
                "step_statuses": statuses,
            }
        step = steps[index]
        statuses[step["step_id"]] = "running"
        self.event_sink(
            "step.started",
            {"step": step, "step_index": index + 1, "step_total": len(steps)},
            step["step_id"],
        )
        return {
            "active_step": step,
            "active_step_index": index,
            "step_statuses": statuses,
            "status": "running",
        }

    def _assemble_step_context(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        step = AgentPlan.model_validate(state["plan"]).steps[
            state["active_step_index"]
        ]
        snapshot = self.context.assemble(
            selected_domain_ids=step.domains,
            message=state["message"],
            step=step,
            evidence=[],
            working_memory=self._working_memory(state),
        )
        return {"loaded_tool_ids": snapshot.tool_ids}

    @staticmethod
    def _working_memory(state: AgentTaskState) -> dict[str, Any]:
        return build_working_memory(
            plan=AgentPlan.model_validate(state["plan"]),
            step_statuses=state.get("step_statuses", {}),
            active_step_index=state.get("active_step_index", -1),
            errors=state.get("errors", []),
        )

    def _serialize_model_payload(
        self,
        state: AgentTaskState,
        payload: Any,
        *,
        max_chars: int,
        layer: str,
        step_id: str | None = None,
    ) -> str:
        serialized, compacted = serialize_bounded_json(
            payload,
            max_chars=max_chars,
        )
        if compacted:
            self.event_sink(
                "context.compacted",
                {
                    "layer": layer,
                    "strategy": "deterministic_bounded_json",
                    "size_chars": len(serialized),
                    "max_chars": max_chars,
                    "restorable_references_preserved": True,
                },
                step_id,
            )
        return serialized

    def _bind_action(self, state: AgentTaskState) -> dict[str, Any]:
        step = AgentPlan.model_validate(state["plan"]).steps[
            state["active_step_index"]
        ]
        if step.kind == "model_reasoning":
            return {"action": None}
        outputs = state.get("step_outputs", {})
        goal = AgentGoalSpec.model_validate(state["goal"])
        if step.capability_id == "collection.run.start":
            input_model = CollectionRunStart(
                source_ids=(
                    list(step.arguments.get("source_ids", []))
                    or state.get("retry_source_ids", [])
                ),
                trigger_type=(
                    "retry" if state.get("retry_count", 0) else "agent"
                ),
            )
        elif step.capability_id == "intelligence.timeline.query":
            published_to = goal.time_window.published_to or datetime.now(
                timezone.utc
            )
            published_from = goal.time_window.published_from or (
                published_to
                - timedelta(hours=goal.time_window.lookback_hours)
            )
            input_model = TimelineQuery(
                published_from=published_from,
                published_to=published_to,
                limit=200,
            )
        elif step.capability_id == "intelligence.search":
            published_to = goal.time_window.published_to or datetime.now(
                timezone.utc
            )
            published_from = goal.time_window.published_from or (
                published_to
                - timedelta(hours=goal.time_window.lookback_hours)
            )
            input_model = IntelligenceSearchInput(
                query=goal.topic,
                scopes=["intelligence"],
                limit=50,
                published_from=published_from,
                published_to=published_to,
            )
        elif step.capability_id == "web.search.collect":
            local_search = self._output_for_capability(
                state,
                "intelligence.search",
            )
            hours = goal.time_window.lookback_hours
            freshness = (
                "pd"
                if hours <= 24
                else "pw"
                if hours <= 24 * 7
                else "pm"
                if hours <= 24 * 31
                else "py"
            )
            input_model = WebSearchCollectInput(
                query=f"{goal.topic} 最新动态",
                limit=min(max(goal.max_items * 2, 6), 20),
                freshness=freshness,
                local_result_count=len(local_search.get("items", [])),
                minimum_results=goal.max_items,
            )
        elif step.capability_id in {
            "research.recommend",
            "research.trend_brief",
        }:
            collection = self._output_for_capability(
                state,
                "collection.run.start",
            )
            if step.capability_id == "research.recommend":
                candidate_ids = []
            else:
                recommendations = self._output_for_capability(
                    state,
                    "research.recommend",
                ).get("items", [])
                candidate_ids = [
                    item.get("information_id")
                    or item.get("information_ids", [None])[0]
                    for item in recommendations
                ]
                candidate_ids = [
                    item_id for item_id in candidate_ids if item_id
                ]
            input_model = ResearchInput(
                candidate_ids=[
                    str(item_id) for item_id in candidate_ids
                ],
                topic=goal.topic,
                lookback_hours=goal.time_window.lookback_hours,
                fallback_lookback_hours=min(
                    max(goal.time_window.lookback_hours * 3, 72),
                    24 * 30,
                ),
                allow_workspace_backfill=(
                    step.capability_id == "research.recommend"
                ),
                published_from=goal.time_window.published_from,
                published_to=goal.time_window.published_to,
                limit=goal.max_items,
                rank_by=goal.ranking_criterion,
                run_id=collection.get("id"),
                conversation_id=state["conversation_id"],
                user_goal=state["message"],
                output_max_chars=int(
                    step.arguments.get("output_max_chars", 1600)
                ),
            )
        else:
            schema = TOOL_SCHEMAS.get(step.capability_id)
            if schema is None:
                return {
                    "status": "failed",
                    "errors": [
                        ErrorEnvelope(
                            code="AGENT_ACTION_UNSUPPORTED",
                            message=step.capability_id,
                            source="capability",
                        ).model_dump(mode="json")
                    ],
                }
            input_model = schema.model_validate(step.arguments)
        canonical = input_model.model_dump(mode="json")
        digest = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return {
            "action": ActionEnvelope(
                turn_id=state["turn_id"],
                step_id=step.step_id,
                domain_id=step.domains[0],
                capability_id=step.capability_id,
                canonical_input=canonical,
                input_digest=digest,
                acceptance_policy=step.acceptance_policy,
                side_effect=step.side_effect,
                risk=step.risk,
            ).model_dump(mode="json")
        }

    @staticmethod
    def _output_for_capability(
        state: AgentTaskState,
        capability_id: str,
    ) -> dict[str, Any]:
        outputs = state.get("step_outputs", {})
        for step in state.get("plan", {}).get("steps", []):
            if step.get("capability_id") == capability_id:
                return outputs.get(step["step_id"], {})
        return {}

    def _validate_action(self, state: AgentTaskState) -> dict[str, Any]:
        if state["active_step"]["kind"] == "model_reasoning":
            return {}
        action = state.get("action")
        if action is None:
            return {"status": "failed"}
        try:
            TOOL_SCHEMAS[action["capability_id"]].model_validate(
                action["canonical_input"]
            )
            return {}
        except Exception as error:
            return {
                "status": "failed",
                "errors": [
                    ErrorEnvelope(
                        code="AGENT_ACTION_INVALID",
                        message=str(error),
                        source="input",
                    ).model_dump(mode="json")
                ],
            }

    def _capability_gate(self, state: AgentTaskState) -> dict[str, Any]:
        if state["active_step"]["kind"] == "model_reasoning":
            return {}
        capability_id = state["action"]["capability_id"]
        if capability_id in self.executor.disabled_capabilities:
            return {
                "status": "failed",
                "errors": [
                    ErrorEnvelope(
                        code="CAPABILITY_DISABLED",
                        message=f"{capability_id} is disabled.",
                        source="capability",
                    ).model_dump(mode="json")
                ],
            }
        if (
            state["action"]["risk"] in {"medium", "high"}
            and not state.get("approval_granted")
        ):
            return {"status": "waiting_approval"}
        return {}

    def _approval_placeholder(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        action = state["action"]
        payload = interrupt(
            {
                "kind": "approval",
                "turn_id": state["turn_id"],
                "step_id": action["step_id"],
                "capability_id": action["capability_id"],
                "input_digest": action["input_digest"],
            }
        )
        if payload.get("approved") is not True:
            errors = list(state.get("errors", []))
            errors.append(
                ErrorEnvelope(
                    code="APPROVAL_REJECTED",
                    message="用户拒绝了该动作。",
                    source="capability",
                    partial=True,
                ).model_dump(mode="json")
            )
            return {
                "status": "running",
                "approval_rejected": True,
                "errors": errors,
            }
        return {
            "status": "running",
            "approval_granted": True,
            "approval_rejected": False,
        }

    def _route_executor(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _execution_context(self, state: AgentTaskState) -> ExecutionContext:
        action = state["action"]
        return ExecutionContext(
            request_id=state["request_id"],
            actor_type="internal_agent",
            actor_id="workspace-agent",
            idempotency_key=(
                f"{state['turn_id']}:{action['step_id']}:"
                f"{action['capability_id']}:{action['input_digest']}:"
                f"retry-{state.get('retry_count', 0)}"
            ),
        )

    def _execute_capability(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        return self._invoke_bound_tool(state, use_agent=False)

    def _execute_domain_agent(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        if state["active_step"]["kind"] == "model_reasoning":
            return self._execute_model_reasoning(state)
        invoked = self._invoke_bound_tool(state, use_agent=True)
        if "step_outputs" not in invoked:
            return invoked
        capability_id = state["action"]["capability_id"]
        if capability_id == "research.recommend":
            if self._research_model_enabled():
                return self._synthesize_research_analysis(state, invoked)
            return invoked
        if capability_id != "research.trend_brief":
            return invoked
        step_id = state["action"]["step_id"]
        output = invoked["step_outputs"][step_id]
        recommendation = self._output_for_capability(
            state,
            "research.recommend",
        )
        precomputed = recommendation.get("precomputed_trend_synthesis")
        if precomputed:
            output["synthesis"] = precomputed
            output["trends"] = precomputed.get("key_findings", [])
            output["analysis_mode"] = "model"
            if not output["trends"]:
                output["status"] = "partial"
            invoked["step_outputs"][step_id] = output
            return invoked
        if state.get("research_analysis_failed"):
            output["analysis_mode"] = "deterministic_fallback"
            invoked["step_outputs"][step_id] = output
            return invoked
        if not self._research_model_enabled():
            return invoked
        try:
            synthesis = self._invoke_structured_model(
                TrendSynthesis,
                [
                    SystemMessage(
                        content=(
                            "只综合给定的有界证据；每条 finding 必须引用至少一个"
                            "给定 information_id，不得虚构指标或 HTML。除原始来源"
                            "内容与专有名词外，所有加工后的分析必须使用简体中文。"
                        )
                    ),
                    HumanMessage(
                        content=self._serialize_model_payload(
                            state,
                            {
                                "goal": state["goal"],
                                "bounded_research": output,
                                "working_memory": self._working_memory(
                                    state
                                ),
                            },
                            max_chars=12000,
                            layer="trend_synthesis",
                            step_id=step_id,
                        )
                    ),
                ]
            )
            validated = (
                synthesis
                if isinstance(synthesis, TrendSynthesis)
                else TrendSynthesis.model_validate(synthesis)
            ).model_copy(update={"synthesis_mode": "model"})
            validated, _repaired = self._ground_trend_synthesis(
                validated,
                [
                    str(item_id)
                    for item_id in output.get(
                        "evidence_information_ids",
                        [],
                    )
                ],
            )
            output["synthesis"] = validated.model_dump(mode="json")
            output["trends"] = [
                item.model_dump(mode="json")
                for item in validated.key_findings
            ]
            invoked["step_outputs"][step_id] = output
            return invoked
        except Exception as error:
            errors = list(state.get("errors", []))
            errors.append(
                ErrorEnvelope(
                    code="AGENT_SYNTHESIS_PROVIDER_FAILED",
                    message=(
                        "模型趋势综合未通过校验；"
                        "已保留能力层生成的中文趋势与证据引用。"
                    ),
                    source="provider",
                    retryable=True,
                    partial=True,
                    details={
                        "provider_error": str(error)[:500],
                        "fallback": "deterministic_trend",
                    },
                ).model_dump(mode="json")
            )
            invoked["errors"] = errors
            output["analysis_mode"] = "deterministic_fallback"
            invoked["step_outputs"][step_id] = output
            invoked["status"] = "running"
            invoked["research_analysis_failed"] = True
            return invoked

    def _research_model_enabled(self) -> bool:
        return isinstance(self.synthesis_model, ChatOpenAI) or bool(
            getattr(
                self.synthesis_model,
                "enable_research_synthesis",
                False,
            )
        )

    def _invoke_structured_model(
        self,
        schema,
        messages: list,
    ):
        metadata = getattr(self.synthesis_model, "metadata", None) or {}
        if isinstance(self.synthesis_model, ChatOpenAI):
            structured = self.synthesis_model.with_structured_output(
                schema,
                method=str(
                    metadata.get(
                        "structured_output_method",
                        "function_calling",
                    )
                ),
                include_raw=True,
            )
            envelope = structured.invoke(messages)
            if not isinstance(envelope, dict):
                raise ValueError("AGENT_RESEARCH_MODEL_ENVELOPE_INVALID")
            parsed = envelope.get("parsed")
            if parsed is None:
                raw = envelope.get("raw")
                try:
                    parsed = schema.model_validate(
                        self._decode_structured_raw(raw)
                    )
                except Exception as first_error:
                    try:
                        retry_model = self.synthesis_model
                        if metadata.get("json_object_retry"):
                            retry_model = self.synthesis_model.bind(
                                response_format={"type": "json_object"},
                                max_tokens=None,
                            )
                        retry = retry_model.invoke(
                            [
                                SystemMessage(
                                    content=(
                                        "上一次函数调用结构未通过校验。"
                                        "请只返回一个 JSON 对象，不要 Markdown；"
                                        "必须输出 JSON，且不得省略必填字段。"
                                        "内容必须符合以下 JSON Schema："
                                        f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)[:8000]}"
                                    )
                                ),
                                *messages,
                            ]
                        )
                        parsed = schema.model_validate(
                            self._decode_structured_raw(retry)
                        )
                    except Exception as retry_error:
                        raise ValueError(
                            "AGENT_RESEARCH_MODEL_RESPONSE_INVALID:"
                            f"{type(retry_error).__name__}:"
                            f"{str(envelope.get('parsing_error') or first_error)[:500]}"
                        ) from retry_error
            return (
                parsed
                if isinstance(parsed, schema)
                else schema.model_validate(parsed)
            )
        try:
            structured = self.synthesis_model.with_structured_output(schema)
            value = structured.invoke(messages)
            return (
                value
                if isinstance(value, schema)
                else schema.model_validate(value)
            )
        except (NotImplementedError, AttributeError, ValueError, TypeError):
            response = self.synthesis_model.invoke(messages)
            content = response.content
            if not isinstance(content, str):
                raise ValueError("AGENT_RESEARCH_MODEL_RESPONSE_INVALID")
            return schema.model_validate(
                self._decode_structured_content(content)
            )

    @classmethod
    def _decode_structured_raw(cls, raw: Any) -> dict[str, Any]:
        candidates: list[Any] = []
        if raw is not None:
            candidates.append(getattr(raw, "content", ""))
            for attribute in ("tool_calls", "invalid_tool_calls"):
                for tool_call in getattr(raw, attribute, []) or []:
                    if not isinstance(tool_call, dict):
                        continue
                    arguments = tool_call.get("args")
                    function = tool_call.get("function")
                    if arguments is None and isinstance(function, dict):
                        arguments = function.get("arguments")
                    candidates.append(arguments)
            additional = getattr(raw, "additional_kwargs", {}) or {}
            for tool_call in additional.get("tool_calls", []) or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                if isinstance(function, dict):
                    candidates.append(function.get("arguments"))

        last_error: Exception | None = None
        for candidate in candidates:
            if isinstance(candidate, dict):
                return candidate
            if candidate in (None, "", []):
                continue
            try:
                return cls._decode_structured_content(candidate)
            except Exception as error:
                last_error = error
        raise ValueError("AGENT_STRUCTURED_PAYLOAD_MISSING") from last_error

    @staticmethod
    def _decode_structured_content(content: Any) -> dict[str, Any]:
        if isinstance(content, list):
            content = "\n".join(
                str(item.get("text", ""))
                if isinstance(item, dict)
                else str(item)
                for item in content
            )
        text = str(content).strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("AGENT_RESEARCH_MODEL_JSON_MISSING")
        value = json.loads(text[start : end + 1])
        if not isinstance(value, dict):
            raise ValueError("AGENT_RESEARCH_MODEL_JSON_OBJECT_REQUIRED")
        return value

    def _synthesize_research_analysis(
        self,
        state: AgentTaskState,
        invoked: dict[str, Any],
    ) -> dict[str, Any]:
        step_id = state["action"]["step_id"]
        output = invoked["step_outputs"][step_id]
        candidates = list(output.get("items", []))
        self.event_sink(
            "model.research.started",
            {
                "effective_model_id": state.get("effective_model_id"),
                "candidate_count": len(candidates),
            },
            step_id,
        )
        try:
            analysis = self._invoke_structured_model(
                ResearchAnalysisSynthesis,
                [
                    SystemMessage(
                        content=(
                            "只对给定的有界候选进行排序，并生成一份推荐与趋势共享分析。"
                            "推荐 ID 和每条趋势引用只能来自给定 information_ids；"
                            "不得虚构当前事实、来源、指标、ID、HTML 或工具结果。"
                            "默认输出语言为简体中文：除原始标题、原始摘要、来源名和"
                            "专有名词外，recommendation_overview、推荐理由、趋势标题、"
                            "趋势说明和不确定性必须使用中文。候选为空时，推荐和"
                            "finding 必须为空，并用中文说明证据缺口。每条推荐还要"
                            "给出 important/watch/normal 分级和最多 6 个简短中文"
                            "标签；标签不得虚构候选中没有依据的能力。"
                        )
                    ),
                    HumanMessage(
                        content=self._serialize_model_payload(
                            state,
                            {
                                "goal": state["goal"],
                                "candidates": candidates,
                                "working_memory": self._working_memory(
                                    state
                                ),
                            },
                            max_chars=16000,
                            layer="research_candidates",
                            step_id=step_id,
                        )
                    ),
                ],
            )
            decisions = list(analysis.recommendations)
            requested = AgentGoalSpec.model_validate(
                state["goal"]
            ).max_items
            (
                selected,
                selection_repaired,
                model_selected_count,
            ) = self._ground_recommendation_decisions(
                candidates,
                decisions,
                requested,
            )
            trend = analysis.trend.model_copy(
                update={"synthesis_mode": "model"}
            )
            trend, citations_repaired = self._ground_trend_synthesis(
                trend,
                [item["information_id"] for item in selected],
            )
            output["items"] = selected
            output["evidence_information_ids"] = list(
                dict.fromkeys(item["information_id"] for item in selected)
            )
            output["recommendation_overview"] = (
                self._prefer_chinese_generated_text(
                    analysis.recommendation_overview,
                    (
                        f"已基于 {len(selected)} 条可追溯信息完成影响力排序；"
                        "推荐理由由模型语义判断与能力层真实排序共同形成。"
                    )
                    if selected
                    else "当前时间范围及背景补充中没有可引用信息。",
                )
            )
            output["uncertainties"] = self._localized_uncertainties(
                analysis.uncertainties,
                (
                    "当前结论只基于工作区已保存信息，"
                    "不包含外部阅读量或点赞量。"
                ),
            )
            output["analysis_mode"] = "model"
            output["citations_repaired"] = citations_repaired
            output["selection_repaired"] = selection_repaired
            output["precomputed_trend_synthesis"] = trend.model_dump(
                mode="json"
            )
            output["status"] = (
                "partial"
                if len(selected) < min(requested, len(candidates))
                else "completed"
            )
            invoked["step_outputs"][step_id] = output
            self.event_sink(
                "model.research.completed",
                {
                    "effective_model_id": state.get("effective_model_id"),
                    "selected_count": len(selected),
                    "model_selected_count": model_selected_count,
                    "selection_repaired": selection_repaired,
                    "synthesis_reused_by": "research.trend_brief",
                },
                step_id,
            )
            return invoked
        except Exception as error:
            errors = list(state.get("errors", []))
            reason = self._research_provider_failure_reason(error)
            errors.append(
                ErrorEnvelope(
                    code="AGENT_RESEARCH_MODEL_FAILED",
                    message=(
                        f"模型结构化分析未通过校验：{reason}；"
                        "已保留能力层的真实排序与确定性结果。"
                    ),
                    source="provider",
                    retryable=True,
                    partial=True,
                    details={
                        "provider_error": str(error)[:500],
                        "fallback": "deterministic_research",
                    },
                ).model_dump(mode="json")
            )
            output["analysis_mode"] = "deterministic_fallback"
            output["recommendation_overview"] = (
                "模型结构化分析未通过校验；"
                f"已使用能力层真实排序保留 {len(output.get('items', []))} 条结果。"
            )
            output["uncertainties"] = [
                "本轮推荐理由为确定性后备结果，未采用无效的模型结构化输出。"
            ]
            invoked["step_outputs"][step_id] = output
            invoked["errors"] = errors
            invoked["status"] = "running"
            invoked["research_analysis_failed"] = True
            self.event_sink(
                "model.research.failed",
                {
                    "effective_model_id": state.get(
                        "effective_model_id"
                    ),
                    "reason": reason,
                    "fallback": "deterministic_research",
                },
                step_id,
            )
            return invoked

    @staticmethod
    def _ground_recommendation_decisions(
        candidates: list[dict[str, Any]],
        decisions: list[Any],
        requested: int,
    ) -> tuple[list[dict[str, Any]], bool, int]:
        allowed = {
            str(item["information_id"]): item for item in candidates
        }
        selected: list[dict[str, Any]] = []
        selected_ids: set[str] = set()
        repaired = False
        for decision in decisions:
            information_id = str(decision.information_id)
            if information_id not in allowed or information_id in selected_ids:
                repaired = True
                continue
            item = dict(allowed[information_id])
            item["reason"] = (
                WorkspaceGraphRunner._prefer_chinese_generated_text(
                    decision.reason,
                    str(
                        item.get("reason")
                        or "该信息在真实候选排序中位于前列。"
                    ),
                )
            )
            if decision.priority is not None:
                item["color"] = decision.priority
            generated_tags = [
                WorkspaceGraphRunner._prefer_chinese_tag(tag)
                for tag in decision.tags
            ]
            generated_tags = [
                tag for tag in generated_tags if tag
            ]
            if generated_tags:
                item["tags"] = list(
                    dict.fromkeys(generated_tags)
                )[:6]
            item["ranking_basis"] = [
                *item.get("ranking_basis", []),
                "所选模型基于有界候选完成语义判断",
            ]
            selected.append(item)
            selected_ids.add(information_id)

        model_selected_count = len(selected)
        target = min(requested, len(candidates))
        for candidate in candidates:
            if len(selected) >= target:
                break
            information_id = str(candidate["information_id"])
            if information_id in selected_ids:
                continue
            item = dict(candidate)
            item["ranking_basis"] = [
                *item.get("ranking_basis", []),
                "能力层真实排序补齐模型未覆盖候选",
            ]
            selected.append(item)
            selected_ids.add(information_id)
            repaired = True

        return selected, repaired, model_selected_count

    @staticmethod
    def _prefer_chinese_generated_text(
        value: Any,
        fallback: str,
    ) -> str:
        text = str(value or "").strip()
        han_count = len(re.findall(r"[\u3400-\u9fff]", text))
        latin_count = len(re.findall(r"[A-Za-z]", text))
        if han_count >= 4 and han_count * 2 >= latin_count:
            return text
        return fallback

    @staticmethod
    def _prefer_chinese_tag(value: Any) -> str:
        text = str(value or "").strip()[:24]
        if len(re.findall(r"[\u3400-\u9fff]", text)) >= 2:
            return text
        return ""

    @staticmethod
    def _research_provider_failure_reason(error: Exception) -> str:
        value = f"{type(error).__name__}:{str(error)}"
        if "AGENT_STRUCTURED_PAYLOAD_MISSING" in value:
            return "模型未返回工具参数或 JSON 正文"
        if "JSON" in value or "json" in value:
            return "模型返回的 JSON 格式无效或被截断"
        if "ValidationError" in value or "validation" in value.lower():
            return "模型返回缺少必填字段或字段类型不正确"
        if "timeout" in value.lower():
            return "模型服务响应超时"
        return "模型返回无法按研究结果契约解析"

    @classmethod
    def _localized_uncertainties(
        cls,
        values: list[str],
        fallback: str,
    ) -> list[str]:
        localized = [
            cls._prefer_chinese_generated_text(value, fallback)
            for value in values
        ]
        if not localized:
            localized = [fallback]
        return list(dict.fromkeys(localized))

    @staticmethod
    def _ground_trend_synthesis(
        trend: TrendSynthesis,
        selected_ids: list[str],
    ) -> tuple[TrendSynthesis, bool]:
        selected = set(selected_ids)
        repaired = False

        def ground_findings(findings):
            nonlocal repaired
            if not selected_ids:
                if findings:
                    repaired = True
                return []
            grounded = []
            for finding in findings:
                valid = [
                    information_id
                    for information_id in finding.information_ids
                    if information_id in selected
                ]
                if not valid:
                    valid = list(selected_ids)
                if valid != finding.information_ids:
                    repaired = True
                grounded.append(
                    finding.model_copy(update={"information_ids": valid})
                )
            return grounded

        valid_summary_ids = [
            information_id
            for information_id in trend.information_ids
            if information_id in selected
        ]
        if valid_summary_ids != trend.information_ids:
            repaired = True
        if selected_ids and not valid_summary_ids:
            valid_summary_ids = list(selected_ids)
            repaired = True

        def localize_findings(
            findings,
            *,
            title_fallback: str,
            summary_fallback: str,
        ):
            return [
                finding.model_copy(
                    update={
                        "title": (
                            WorkspaceGraphRunner
                            ._prefer_chinese_generated_text(
                                finding.title,
                                title_fallback,
                            )
                        ),
                        "summary": (
                            WorkspaceGraphRunner
                            ._prefer_chinese_generated_text(
                                finding.summary,
                                summary_fallback,
                            )
                        ),
                    }
                )
                for finding in ground_findings(findings)
            ]

        return (
            trend.model_copy(
                update={
                    "overview": (
                        WorkspaceGraphRunner._prefer_chinese_generated_text(
                            trend.overview,
                            (
                                f"已基于 {len(selected_ids)} 条可追溯信息"
                                "完成趋势归纳。"
                            )
                            if selected_ids
                            else "当前没有可引用信息，无法形成趋势判断。",
                        )
                    ),
                    "key_findings": localize_findings(
                        trend.key_findings,
                        title_fallback="趋势判断",
                        summary_fallback=(
                            "该判断仅基于本轮已引用的真实信息。"
                        ),
                    ),
                    "why_it_matters": localize_findings(
                        trend.why_it_matters,
                        title_fallback="为什么重要",
                        summary_fallback=(
                            "该影响判断以本轮可追溯证据为边界。"
                        ),
                    ),
                    "differences": localize_findings(
                        trend.differences,
                        title_fallback="差异",
                        summary_fallback=(
                            "入选信息来自不同事件或应用角度。"
                        ),
                    ),
                    "uncertainties": (
                        WorkspaceGraphRunner._localized_uncertainties(
                            trend.uncertainties,
                            "结论仅适用于本轮已引用的工作区信息。",
                        )
                    ),
                    "information_ids": valid_summary_ids,
                    "synthesis_mode": "model",
                }
            ),
            repaired,
        )

    def _execute_model_reasoning(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        if self._cancelled(state):
            return {"status": "cancelled", "cancel_requested": True}
        step = AgentPlan.model_validate(state["plan"]).steps[
            state["active_step_index"]
        ]
        step_id = step.step_id
        basis = str(
            step.arguments.get(
                "response_basis",
                "mixed" if state.get("step_outputs") else "conversation_context",
            )
        )
        if basis not in {
            "conversation_context",
            "tool_evidence",
            "mixed",
        }:
            basis = "mixed"
        bounded_payload = {
            "user_message": state["message"],
            "goal": state["goal"],
            "conversation_context": state.get("conversation_context", {}),
            "completed_step_outputs": state.get("step_outputs", {}),
            "working_memory": self._working_memory(state),
        }
        self.event_sink(
            "model.reasoning.started",
            {
                "effective_model_id": state.get("effective_model_id"),
                "basis": basis,
            },
            step_id,
        )
        try:
            response = self.synthesis_model.invoke(
                [
                    SystemMessage(
                        content=(
                            "使用所选模型自身的推理能力回答用户当前请求。只能使用下方"
                            "提供的有界会话上下文和已完成步骤输出；此步骤不提供工具。"
                            "默认使用简体中文，除原始来源内容和专有名词外，所有加工后的"
                            "分析、结论、不确定性与总结都必须为中文。缺少条目级证据时"
                            "必须明确说明，不得虚构工作区 ID、引用、当前事实、工具结果"
                            "或影响力数字。只返回纯文本，不返回 HTML 或工具 JSON。"
                        )
                    ),
                    HumanMessage(
                        content=self._serialize_model_payload(
                            state,
                            bounded_payload,
                            max_chars=16000,
                            layer="model_reasoning",
                            step_id=step_id,
                        )
                    ),
                ]
            )
            content = response.content
            if isinstance(content, list):
                content = "\n".join(
                    str(item.get("text", ""))
                    if isinstance(item, dict)
                    else str(item)
                    for item in content
                )
            content = str(content).strip()
            content = self._prefer_chinese_generated_text(
                content,
                (
                    "所选模型未按默认中文返回有效回答；"
                    "本轮未改写原始来源内容，也未补造事实。"
                ),
            )
            information_ids = list(
                dict.fromkeys(
                    [
                        *state.get("joined_evidence_ids", []),
                        *self._conversation_information_ids(state),
                    ]
                )
            )[:20]
            boundary = (
                "回答仅基于本会话中提供的有界内容；"
                "未调用工具，也不代表工作区实时排名。"
                if basis == "conversation_context"
                else "回答基于已完成步骤输出；未提供的事实未作推断。"
            )
            output = ModelReasoningOutput(
                content=content,
                basis=basis,
                evidence_boundary=boundary,
                information_ids=information_ids,
                effective_model_id=str(
                    state.get("effective_model_id") or "unknown"
                ),
            ).model_dump(mode="json")
            outputs = dict(state.get("step_outputs", {}))
            outputs[step_id] = output
            self.event_sink(
                "model.reasoning.completed",
                {
                    "effective_model_id": output["effective_model_id"],
                    "basis": basis,
                    "content_chars": len(content),
                },
                step_id,
            )
            return {"step_outputs": outputs}
        except Exception as error:
            errors = list(state.get("errors", []))
            errors.append(
                ErrorEnvelope(
                    code="AGENT_REASONING_PROVIDER_FAILED",
                    message=str(error),
                    source="provider",
                    retryable=True,
                    partial=bool(state.get("step_outputs")),
                ).model_dump(mode="json")
            )
            return {"errors": errors, "status": "failed"}

    @staticmethod
    def _conversation_information_ids(
        state: AgentTaskState,
    ) -> list[str]:
        ids: list[str] = []
        references = state.get("conversation_context", {}).get(
            "prior_turn_refs",
            [],
        )
        for reference in references[:3]:
            for block in reference.get("result_summaries", [])[:6]:
                data = block.get("data", {})
                if data.get("information_id"):
                    ids.append(str(data["information_id"]))
                ids.extend(
                    str(item_id)
                    for item_id in data.get("information_ids", [])
                    if item_id
                )
                for item in data.get("items", [])[:3]:
                    if item.get("information_id"):
                        ids.append(str(item["information_id"]))
        return list(dict.fromkeys(ids))

    def _execute_domain_workflow(
        self,
        state: AgentTaskState,
    ) -> dict[str, Any]:
        return self._invoke_bound_tool(state, use_agent=False)

    def _invoke_bound_tool(
        self,
        state: AgentTaskState,
        *,
        use_agent: bool,
    ) -> dict[str, Any]:
        if self._cancelled(state):
            return {"status": "cancelled", "cancel_requested": True}
        action = state["action"]
        step_id = action["step_id"]
        capability_id = action["capability_id"]
        self.event_sink(
            "tool.started",
            {"capability_id": capability_id},
            step_id,
        )
        tool = build_capability_tool(
            self.executor,
            capability_id,
            lambda: self._execution_context(state),
        )
        try:
            if use_agent:
                agent = create_agent(
                    model=BoundActionChatModel(
                        tool_name=tool.name,
                        tool_input=action["canonical_input"],
                    ),
                    tools=[tool],
                    system_prompt=(
                        "Execute only the already validated action. "
                        "Do not invent identifiers or call another tool."
                    ),
                )
                agent_result = agent.invoke(
                    {"messages": [HumanMessage(content="Execute action.")]}
                )
                tool_messages = [
                    message
                    for message in agent_result["messages"]
                    if isinstance(message, ToolMessage)
                ]
                if not tool_messages:
                    raise RuntimeError("AGENT_TOOL_RESULT_MISSING")
                content = tool_messages[-1].content
                output = (
                    json.loads(content)
                    if isinstance(content, str)
                    else content
                )
            else:
                output = tool.invoke(action["canonical_input"])
            self.event_sink(
                "tool.completed",
                {"capability_id": capability_id, "status": output.get("status", "completed")},
                step_id,
            )
            outputs = dict(state.get("step_outputs", {}))
            outputs[step_id] = output
            return {"step_outputs": outputs}
        except CapabilityExecutionError as error:
            envelope = ErrorEnvelope(
                code=error.code,
                message=str(error),
                source="capability",
                retryable=False,
            )
        except Exception as error:
            envelope = ErrorEnvelope(
                code="AGENT_STEP_EXECUTION_FAILED",
                message=str(error),
                source="system",
                retryable=False,
            )
        errors = list(state.get("errors", []))
        errors.append(envelope.model_dump(mode="json"))
        return {"errors": errors, "status": "failed"}

    def _record_result(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _join_results(self, state: AgentTaskState) -> dict[str, Any]:
        evidence_ids: list[str] = []
        for output in state.get("step_outputs", {}).values():
            evidence_ids.extend(output.get("evidence_information_ids", []))
            for item in output.get("items", []):
                evidence_ids.extend(item.get("information_ids", []))
                if item.get("information_id"):
                    evidence_ids.append(item["information_id"])
        return {"joined_evidence_ids": list(dict.fromkeys(evidence_ids))}

    def _inspect_outcome(self, state: AgentTaskState) -> dict[str, Any]:
        statuses = dict(state.get("step_statuses", {}))
        step = AgentPlan.model_validate(state["plan"]).steps[
            state["active_step_index"]
        ]
        step_id = step.step_id
        if state.get("approval_rejected"):
            statuses[step_id] = "skipped_approval"
            return {
                "active_step_index": state.get("active_step_index", 0) + 1,
                "active_step": None,
                "step_statuses": statuses,
                "status": "running",
            }
        output = state.get("step_outputs", {}).get(step_id)
        gaps = self._acceptance_gaps(step, output, state)
        errors = list(state.get("errors", []))
        partial_output = bool(
            output is not None and output.get("status") == "partial"
        )
        recoverable_gaps = bool(
            gaps
            and self._is_recoverable_coverage_gap(step, output, gaps, state)
        )
        if recoverable_gaps or (partial_output and not gaps):
            statuses[step_id] = "partial"
            reported_gaps = gaps or list(output.get("coverage_gaps", []))
            errors.append(
                ErrorEnvelope(
                    code="AGENT_OUTCOME_PARTIAL",
                    message=";".join(reported_gaps)
                    or "能力已执行，但结果覆盖不足。",
                    source="business",
                    retryable=False,
                    partial=True,
                    details={
                        "step_id": step_id,
                        "gaps": reported_gaps,
                    },
                ).model_dump(mode="json")
            )
        elif gaps:
            statuses[step_id] = "failed"
            errors.append(
                ErrorEnvelope(
                    code="AGENT_OUTCOME_REJECTED",
                    message=";".join(gaps),
                    source="business",
                    retryable=True,
                    partial=bool(state.get("step_outputs")),
                    details={"step_id": step_id, "gaps": gaps},
                ).model_dump(mode="json")
            )
        else:
            statuses[step_id] = "completed"
        self.event_sink(
            "step.outcome",
            {
                "status": statuses[step_id],
                "gaps": gaps,
            },
            step_id,
        )
        return {
            "active_step_index": state.get("active_step_index", 0) + 1,
            "active_step": None,
            "step_statuses": statuses,
            "errors": errors,
            "status": (
                "failed"
                if gaps and not recoverable_gaps
                else "running"
            ),
        }

    @staticmethod
    def _is_recoverable_coverage_gap(
        step,
        output: dict[str, Any] | None,
        gaps: list[str],
        state: AgentTaskState,
    ) -> bool:
        del state
        if output is None:
            return False
        if step.acceptance_policy.id == "information_results.v1":
            return all(
                gap.startswith("items_below_minimum:")
                for gap in gaps
            )
        if step.acceptance_policy.id == "synthesis_grounded.v1":
            return (
                bool(output.get("synthesis"))
                and not output.get("evidence_information_ids")
                and gaps == ["findings_below_minimum"]
            )
        return False

    def _acceptance_gaps(
        self,
        step,
        output: dict[str, Any] | None,
        state: AgentTaskState,
    ) -> list[str]:
        if output is None:
            return ["missing_output"]
        policy = step.acceptance_policy
        if policy.id == "capability_effect.v1":
            return [] if output.get("status") != "failed" else ["effect_failed"]
        if policy.id == "artifact_created.v1":
            return [] if output.get("artifact_id") else ["missing_artifact_id"]
        if policy.id == "contextual_response.v1":
            content = str(output.get("content", "")).strip()
            minimum = max(1, int(policy.params.get("min_chars", 1)))
            gaps = []
            if len(content) < minimum:
                gaps.append(
                    f"response_below_minimum:{len(content)}<{minimum}"
                )
            if output.get("basis") not in {
                "conversation_context",
                "tool_evidence",
                "mixed",
            }:
                gaps.append("missing_response_basis")
            if not output.get("evidence_boundary"):
                gaps.append("missing_evidence_boundary")
            return gaps
        items = output.get("items", [])
        if policy.id == "information_results.v1":
            minimum = max(0, int(policy.params.get("min_items", 1)))
            if len(items) < minimum:
                return [f"items_below_minimum:{len(items)}<{minimum}"]
            gaps: list[str] = []
            for item in items:
                ids = item.get("information_ids") or [
                    item.get("information_id") or item.get("id")
                ]
                if not ids or not all(ids):
                    gaps.append("missing_information_id")
                if step.capability_id == "research.recommend":
                    if not str(item.get("app_path", "")).startswith(
                        "/timeline?"
                    ):
                        gaps.append("invalid_app_path")
                    for field in (
                        "source_id",
                        "source_name",
                        "source_url",
                        "ranking_basis",
                    ):
                        if not item.get(field):
                            gaps.append(f"missing_{field}")
            return list(dict.fromkeys(gaps))
        if policy.id == "synthesis_grounded.v1":
            synthesis = output.get("synthesis")
            if not synthesis:
                return ["missing_synthesis"]
            selected = set(
                self._output_for_capability(
                    state,
                    "research.recommend",
                ).get("evidence_information_ids", [])
            )
            if not selected:
                selected = {
                    item.get("information_id")
                    for item in self._output_for_capability(
                        state,
                        "research.recommend",
                    ).get("items", [])
                    if item.get("information_id")
                }
            findings = [
                *synthesis.get("key_findings", []),
                *synthesis.get("why_it_matters", []),
                *synthesis.get("differences", []),
            ]
            minimum = int(policy.params.get("min_findings", 1))
            if len(findings) < minimum:
                return ["findings_below_minimum"]
            if any(
                not finding.get("information_ids")
                or not set(finding["information_ids"]).issubset(selected)
                for finding in findings
            ):
                return ["ungrounded_finding"]
            return []
        return ["unknown_acceptance_policy"]

    def _control_failure(self, state: AgentTaskState) -> dict[str, Any]:
        count = state.get("replan_count", 0)
        plan = AgentPlan.model_validate(state.get("plan", {}))
        if count < plan.max_replans:
            return {
                "status": "running",
                "replan_count": count + 1,
                "replan_requested": True,
                "active_step_index": 0,
                "active_step": None,
            }
        return {
            "status": "failed",
            "replan_requested": False,
        }

    def _compose_result(self, state: AgentTaskState) -> dict[str, Any]:
        plan = AgentPlan.model_validate(state["plan"])
        goal = AgentGoalSpec.model_validate(state["goal"])
        outputs = state.get("step_outputs", {})
        collection = self._output_for_capability(
            state,
            "collection.run.start",
        )
        web_search = self._output_for_capability(
            state,
            "web.search.collect",
        )
        recommendation_output = self._output_for_capability(
            state,
            "research.recommend",
        )
        if not recommendation_output:
            recommendation_output = self._output_for_capability(
                state,
                "intelligence.recommend",
            )
        recommendations = recommendation_output.get("items", [])[
            : goal.max_items
        ]
        synthesis_output = self._output_for_capability(
            state,
            "research.trend_brief",
        )
        errors = [
            ErrorEnvelope.model_validate(item)
            for item in state.get("errors", [])
            if not (
                item.get("code")
                in {
                    "AGENT_PLAN_INVALID",
                    "AGENT_PLAN_COVERAGE_INCOMPLETE",
                    "AGENT_OUTCOME_REJECTED",
                }
                and all(
                    status == "completed"
                    for status in state.get("step_statuses", {}).values()
                )
            )
        ]
        source_errors = collection.get("errors", [])
        for item in source_errors:
            errors.append(
                ErrorEnvelope(
                    code=str(item.get("error_code", "SOURCE_FAILED")),
                    message=str(item.get("message", "来源采集失败")),
                    source="provider",
                    retryable=True,
                    partial=True,
                    details={
                        key: value
                        for key, value in item.items()
                        if key in {"source_id", "source_name"}
                    },
                )
            )
        web_errors = web_search.get("errors", [])
        for item in web_errors:
            errors.append(
                ErrorEnvelope(
                    code=str(
                        item.get("error_code", "WEB_SEARCH_FAILED")
                    ),
                    message=str(item.get("message", "联网补证失败")),
                    source="provider",
                    retryable=True,
                    partial=True,
                    details={"capability_id": "web.search.collect"},
                )
            )
        has_backfill = bool(
            recommendation_output.get("backfilled_information_ids")
        )
        material_errors = [
            error
            for error in errors
            if not (
                has_backfill
                and error.code == "AGENT_OUTCOME_PARTIAL"
                and error.details.get("step_id")
                == next(
                    (
                        step.step_id
                        for step in plan.steps
                        if step.capability_id
                        in {
                            "intelligence.timeline.query",
                            "intelligence.search",
                        }
                    ),
                    None,
                )
            )
        ]
        if state.get("status") == "cancelled":
            status = "cancelled"
        elif (
            len(plan.steps) == 1
            and collection.get("status") == "failed"
        ):
            status = "failed"
        elif any(error.code == "APPROVAL_REJECTED" for error in errors):
            status = "partial"
        elif recommendations and goal.requires_synthesis and not synthesis_output.get(
            "synthesis"
        ):
            status = "partial"
        elif (
            goal.operation_mode
            in {"collect_then_analyze", "analyze_existing"}
            and recommendations
            and len(recommendations) < goal.max_items
        ):
            status = "partial"
        elif recommendations and (
            collection.get("status") == "partial" or material_errors
        ):
            status = "partial"
        elif recommendations:
            status = "complete"
        elif outputs and errors:
            status = "partial"
        elif outputs and not errors:
            status = "complete"
        else:
            status = "failed"
        blocks: list[AgentResultBlock] = [
            AgentResultBlock(
                block_id=f"{state['turn_id']}:plan",
                type="plan_summary",
                title="执行计划",
                data={
                    "goal": goal.model_dump(mode="json"),
                    "steps": [
                        step.model_dump(mode="json") for step in plan.steps
                    ],
                    "selected_domains": plan.selected_domains,
                    "effective_model_id": state.get("effective_model_id"),
                    "context_refs": state.get(
                        "conversation_context",
                        {},
                    ).get("prior_turn_refs", []),
                },
            )
        ]
        model_outputs = [
            (step, outputs.get(step.step_id, {}))
            for step in plan.steps
            if step.kind == "model_reasoning"
        ]
        for step, output in model_outputs:
            if not output.get("content"):
                continue
            blocks.append(
                AgentResultBlock(
                    block_id=(
                        f"{state['turn_id']}:{step.step_id}:model-response"
                    ),
                    type="model_response",
                    title=step.title,
                    data=output,
                )
            )
        if collection:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:collection",
                    type="collection_summary",
                    title="采集结果",
                    data={
                        "run_id": collection.get("id"),
                        "status": collection.get("status"),
                        "items_collected": collection.get("items_collected", 0),
                        "items_added": collection.get("items_added", 0),
                        "errors": source_errors,
                    },
                )
            )
        if web_search:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:web-search",
                    type="collection_summary",
                    title="联网补证",
                    data={
                        "status": web_search.get("status"),
                        "summary": web_search.get("summary"),
                        "skipped": web_search.get("skipped", False),
                        "cache_hit": web_search.get("cache_hit", False),
                        "items_collected": web_search.get(
                            "crawled_count",
                            0,
                        ),
                        "items_added": web_search.get("added_count", 0),
                        "searched_count": web_search.get(
                            "searched_count",
                            0,
                        ),
                        "errors": web_errors,
                    },
                )
            )
        for item in recommendations:
            information_id = item.get("information_id") or item.get(
                "information_ids",
                ["unknown"],
            )[0]
            blocks.append(
                AgentResultBlock(
                    block_id=(
                        f"{state['turn_id']}:signal:{information_id}"
                    ),
                    type="signal_preview",
                    title=item["title"],
                    data=item,
                )
            )
        for step in plan.steps:
            output = outputs.get(step.step_id, {})
            if step.capability_id in {"artifact.search", "agent_pack.search"}:
                matches = output.get("matches", [])
                if matches:
                    blocks.append(
                        AgentResultBlock(
                            block_id=(
                                f"{state['turn_id']}:{step.step_id}:assets"
                            ),
                            type="artifact_list",
                            title=step.title,
                            data={
                                "items": matches,
                                "source_type": step.capability_id,
                            },
                        )
                    )
                continue
            if (
                step.capability_id is None
                or not step.capability_id.startswith("research.")
            ):
                continue
            research_items = output.get("items", [])
            if research_items or (
                step.capability_id == "research.recommend" and output
            ):
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:items",
                        type=(
                            "recommendation_list"
                            if "recommend" in step.capability_id
                            else "information_list"
                        ),
                        title=step.title,
                        data={
                            "items": research_items,
                            "overview": output.get(
                                "recommendation_overview",
                                "",
                            ),
                            "uncertainties": output.get(
                                "uncertainties",
                                [],
                            ),
                            "coverage_gaps": output.get(
                                "coverage_gaps",
                                [],
                            ),
                            "analysis_mode": output.get(
                                "analysis_mode",
                                "deterministic",
                            ),
                            "requested_item_count": output.get(
                                "requested_item_count",
                                len(research_items),
                            ),
                            "effective_lookback_hours": output.get(
                                "effective_lookback_hours",
                                goal.time_window.lookback_hours,
                            ),
                            "backfilled_information_ids": output.get(
                                "backfilled_information_ids",
                                [],
                            ),
                        },
                    )
                )
            if output.get("comparison"):
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:comparison",
                        type="comparison_table",
                        title="带引用的比较",
                        data={"rows": output["comparison"]},
                    )
                )
            if output.get("trends") or output.get("synthesis"):
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:trends",
                        type="trend_summary",
                        title="趋势摘要",
                        data=(
                            output["synthesis"]
                            if output.get("synthesis")
                            else {
                                "overview": "",
                                "key_findings": output["trends"],
                                "why_it_matters": [],
                                "differences": [],
                                "uncertainties": output.get(
                                    "coverage_gaps", []
                                ),
                                "information_ids": output.get(
                                    "evidence_information_ids", []
                                ),
                                "synthesis_mode": "deterministic",
                            }
                        ),
                    )
                )
            if output.get("evidence_information_ids"):
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:evidence",
                        type="evidence_sources",
                        title="信息证据",
                        data={
                            "information_ids": output[
                                "evidence_information_ids"
                            ]
                        },
                    )
                )
        evidence_ids = list(
            dict.fromkeys(
                str(item_id)
                for block in blocks
                if block.type == "evidence_sources"
                for item_id in block.data.get("information_ids", [])
                if item_id
            )
        )
        blocks = [
            block for block in blocks if block.type != "evidence_sources"
        ]
        if evidence_ids:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:evidence",
                    type="evidence_sources",
                    title="信息证据",
                    data={"information_ids": evidence_ids},
                )
            )
        if source_errors:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:partial",
                    type="partial_failure",
                    title="部分来源失败",
                    data={"errors": source_errors, "retryable": True},
                )
            )
        if web_errors:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:web-partial",
                    type="partial_failure",
                    title="联网补证受限",
                    data={
                        "errors": web_errors,
                        "retryable": True,
                        "summary": web_search.get("summary", ""),
                    },
                )
            )
        blocks.append(
            AgentResultBlock(
                block_id=f"{state['turn_id']}:navigation",
                type="navigation_action",
                title="后续操作",
                data={
                    "view_all_path": (
                        f"/timeline?run={collection.get('id', '')}"
                        f"&from=agent&conversation={state['conversation_id']}"
                    ),
                    "run_path": f"/runs?focus={collection.get('id', '')}",
                },
            )
        )
        if (
            goal.operation_mode
            in {"collect_then_analyze", "analyze_existing"}
            and len(recommendations) < goal.max_items
            and not any(
                block.type == "partial_failure" for block in blocks
            )
        ):
            blocks.insert(
                -1,
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:coverage",
                    type="partial_failure",
                    title="候选覆盖不足",
                    data={
                        "requested": goal.max_items,
                        "returned": len(recommendations),
                        "retryable": False,
                    },
                ),
            )
        research_steps = [
            step
            for step in plan.steps
            if step.capability_id is not None
            and step.capability_id.startswith("research.")
        ]
        research_item_count = sum(
            len(outputs.get(step.step_id, {}).get("items", []))
            for step in research_steps
        )
        asset_steps = [
            step
            for step in plan.steps
            if step.capability_id in {"artifact.search", "agent_pack.search"}
        ]
        asset_match_count = sum(
            len(outputs.get(step.step_id, {}).get("matches", []))
            for step in asset_steps
        )
        if len(plan.steps) == 1 and collection:
            if collection.get("status") == "failed":
                message = "采集未完成：当前没有可用的信息来源。"
            elif collection.get("status") == "partial":
                message = (
                    "采集部分完成，已保留成功来源；"
                    f"新增 {collection.get('items_added', 0)} 条。"
                )
            elif int(collection.get("items_added", 0)) == 0:
                message = "采集完成，本次没有新增 AI 信息（已有内容已自动去重）。"
            else:
                message = (
                    f"采集完成，新增 {collection.get('items_added', 0)} 条 AI 信息。"
                )
        elif source_errors:
            failed_names = [
                str(
                    item.get("source_name")
                    or item.get("source_id")
                    or "未知来源"
                )
                for item in source_errors
            ]
            message = (
                f"任务部分完成：{len(source_errors)} 个来源采集失败"
                f"（{'、'.join(failed_names[:3])}），"
                f"已保留 {len(recommendations)} 条可追溯结果。"
            )
        elif status == "failed":
            primary_error = material_errors[0] if material_errors else None
            if primary_error is None:
                message = "任务未完成：没有生成可验证结果，请查看运行详情。"
            elif primary_error.source == "provider":
                message = (
                    f"任务未完成：模型或数据提供方返回异常。"
                    f"{primary_error.message}"
                )
            elif primary_error.source == "input":
                message = (
                    f"任务未完成：输入或计划未通过校验。"
                    f"{primary_error.message}"
                )
            else:
                message = f"任务未完成：{primary_error.message}"
        elif model_outputs:
            completed_model_output = next(
                (
                    output
                    for _step, output in model_outputs
                    if output.get("content")
                ),
                {},
            )
            message = str(
                completed_model_output.get(
                    "content",
                    "已完成基于当前语境的回答。",
                )
            )
        elif research_steps and not recommendations:
            message = (
                "推荐与趋势步骤已执行，但当前时间范围内没有可引用信息；"
                "已保留模型分析的证据边界和数据缺口。"
                if status == "partial"
                else f"研究完成，返回 {research_item_count} 条可追溯结果。"
            )
        elif asset_steps:
            message = f"检索完成，返回 {asset_match_count} 条可定位片段。"
        elif status == "partial":
            message = (
                "部分完成：已返回可追溯推荐与综合分析，但存在明确覆盖缺口；"
                f"当前共 {len(recommendations)} 条信息。"
            )
        else:
            message = (
                "已基于可追溯证据完成影响力排序与综合分析，共选出 "
                f"{len(recommendations)} 条信息。"
            )
        blocks.insert(
            0,
            AgentResultBlock(
                block_id=f"{state['turn_id']}:summary",
                type="result_summary",
                title="本轮总结",
                data={
                    "status": status,
                    "message": message,
                    "recommendation_count": len(recommendations),
                    "evidence_count": len(evidence_ids),
                    "backfilled_count": len(
                        recommendation_output.get(
                            "backfilled_information_ids",
                            [],
                        )
                    ),
                    "web_searched_count": web_search.get(
                        "searched_count",
                        0,
                    ),
                    "web_added_count": web_search.get("added_count", 0),
                    "web_cache_hit": web_search.get(
                        "cache_hit",
                        False,
                    ),
                    "errors": [
                        {
                            "code": error.code,
                            "message": error.message,
                            "source": error.source,
                            "retryable": error.retryable,
                        }
                        for error in material_errors
                    ],
                },
            ),
        )
        result = AgentTurnResult(
            status=status,
            message=message,
            goal=goal,
            plan=plan,
            result_blocks=blocks,
            capability_results=outputs,
            business_run_ids=(
                [collection["id"]] if collection.get("id") else []
            ),
            errors=errors,
            retryable_errors=[error for error in errors if error.retryable],
        )
        for block in blocks:
            self.event_sink(
                "result.block",
                block.model_dump(mode="json"),
                None,
            )
        return {"status": status, "result": result.model_dump(mode="json")}

    def _finalize(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _cancelled(self, state: AgentTaskState) -> bool:
        return bool(
            state.get("cancel_requested")
            or self.cancellation_checker(state["turn_id"])
        )
