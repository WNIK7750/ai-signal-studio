from __future__ import annotations

import hashlib
import json
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

from ai_signal_api.agent_runtime.context import ContextAssembler
from ai_signal_api.agent_runtime.contracts import (
    ActionEnvelope,
    AgentPlan,
    AgentResultBlock,
    AgentTurnResult,
    ErrorEnvelope,
)
from ai_signal_api.agent_runtime.tools import TOOL_SCHEMAS, build_capability_tool
from ai_signal_api.capabilities.core import (
    CapabilityExecutionError,
    CapabilityExecutor,
)
from ai_signal_api.modules.intelligence.agent.schemas import (
    InformationRecommendInput,
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
    """The executable 0.4.0 graph for the first collection research slice."""

    def __init__(
        self,
        *,
        executor: CapabilityExecutor,
        planner_model: BaseChatModel,
        checkpointer: BaseCheckpointSaver,
        event_sink: EventSink | None = None,
        cancellation_checker: Callable[[str], bool] | None = None,
    ) -> None:
        self.executor = executor
        self.planner_model = planner_model
        self.context = ContextAssembler(executor)
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
    ) -> AgentTurnResult:
        final = self.advance(
            turn_id=turn_id,
            conversation_id=conversation_id,
            request_id=request_id,
            message=message,
            cancel_requested=cancel_requested,
            retry_count=retry_count,
            retry_source_ids=retry_source_ids,
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
    ) -> dict[str, Any]:
        state = self.graph.invoke(
            {
                "turn_id": turn_id,
                "conversation_id": conversation_id,
                "request_id": request_id,
                "message": message,
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
                if state["active_step"]["kind"] == "domain_agent"
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
                "N24"
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
        messages = [
            SystemMessage(
                content=(
                    f"{base.system_prompt}\n\n"
                    "可选 Domain Index：collection（采集），"
                    "intelligence（查询与推荐）。"
                    "返回符合 AgentPlan Schema 的单一 json object。"
                )
            ),
            HumanMessage(content=state["message"]),
        ]
        try:
            structured = (
                self.planner_model.with_structured_output(
                    AgentPlan,
                    method="function_calling",
                )
                if isinstance(self.planner_model, ChatOpenAI)
                else self.planner_model.with_structured_output(AgentPlan)
            )
            plan_value = structured.invoke(messages)
            plan = (
                plan_value
                if isinstance(plan_value, AgentPlan)
                else AgentPlan.model_validate(plan_value)
            )
        except (NotImplementedError, AttributeError, ValueError, TypeError):
            response = self.planner_model.invoke(messages)
            content = response.content
            if not isinstance(content, str):
                raise ValueError("AGENT_PLAN_RESPONSE_INVALID")
            plan = AgentPlan.model_validate_json(content)
        self.event_sink(
            "plan.ready",
            {
                "plan": plan.model_dump(mode="json"),
                "planning_mode": plan.planning_mode,
            },
            None,
        )
        return {
            "plan": plan.model_dump(mode="json"),
            "selected_domain_ids": plan.selected_domains,
        }

    def _validate_plan(self, state: AgentTaskState) -> dict[str, Any]:
        try:
            plan = AgentPlan.model_validate(state["plan"])
            allowed = set(self.executor.registry.ids())
            if any(
                step.capability_id not in allowed for step in plan.steps
            ):
                raise ValueError("AGENT_PLAN_CAPABILITY_UNKNOWN")
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
        )
        return {"loaded_tool_ids": snapshot.tool_ids}

    def _bind_action(self, state: AgentTaskState) -> dict[str, Any]:
        step = AgentPlan.model_validate(state["plan"]).steps[
            state["active_step_index"]
        ]
        outputs = state.get("step_outputs", {})
        if step.arguments:
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
        elif step.capability_id == "collection.run.start":
            input_model = CollectionRunStart(
                source_ids=state.get("retry_source_ids", []),
                trigger_type=(
                    "retry" if state.get("retry_count", 0) else "agent"
                ),
            )
        elif step.capability_id == "intelligence.timeline.query":
            input_model = TimelineQuery(
                published_from=datetime.now(timezone.utc)
                - timedelta(hours=24),
                limit=200,
            )
        elif step.capability_id == "intelligence.recommend":
            collection = outputs.get("collect", {})
            query = outputs.get("query", {})
            input_model = InformationRecommendInput(
                candidate_ids=[
                    item["id"] for item in query.get("items", [])
                ],
                topic="Agent",
                limit=min(
                    int(state["plan"].get("constraints", {}).get("max_items", 5)),
                    5,
                ),
                run_id=collection.get("id"),
                conversation_id=state["conversation_id"],
            )
        else:
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

    def _validate_action(self, state: AgentTaskState) -> dict[str, Any]:
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
        return self._invoke_bound_tool(state, use_agent=True)

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
        step_id = state["active_step"]["step_id"]
        output = state.get("step_outputs", {}).get(step_id, {})
        self.event_sink(
            "result.block",
            {"step_id": step_id, "status": output.get("status", "completed")},
            step_id,
        )
        return {}

    def _join_results(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _inspect_outcome(self, state: AgentTaskState) -> dict[str, Any]:
        statuses = dict(state.get("step_statuses", {}))
        step_id = state["active_step"]["step_id"]
        statuses[step_id] = (
            "completed"
            if step_id in state.get("step_outputs", {})
            else "failed"
        )
        return {
            "active_step_index": state.get("active_step_index", 0) + 1,
            "active_step": None,
            "step_statuses": statuses,
            "status": (
                "running"
                if state.get("status") != "cancelled"
                else "cancelled"
            ),
        }

    def _control_failure(self, state: AgentTaskState) -> dict[str, Any]:
        count = state.get("replan_count", 0)
        plan = AgentPlan.model_validate(state.get("plan", {}))
        if count < plan.max_replans:
            return {
                "status": "running",
                "replan_count": count + 1,
                "replan_requested": True,
            }
        return {
            "status": "failed",
            "replan_requested": False,
        }

    def _compose_result(self, state: AgentTaskState) -> dict[str, Any]:
        plan = AgentPlan.model_validate(state["plan"])
        outputs = state.get("step_outputs", {})
        collection = outputs.get("collect", {})
        recommendations = outputs.get("recommend", {}).get("items", [])
        errors = [
            ErrorEnvelope.model_validate(item)
            for item in state.get("errors", [])
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
        if state.get("status") == "cancelled":
            status = "cancelled"
        elif any(error.code == "APPROVAL_REJECTED" for error in errors):
            status = "partial"
        elif recommendations and (
            collection.get("status") == "partial" or errors
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
                data={"steps": [step.model_dump(mode="json") for step in plan.steps]},
            )
        ]
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
        blocks.extend(
            AgentResultBlock(
                block_id=f"{state['turn_id']}:signal:{item['information_id']}",
                type="signal_preview",
                title=item["title"],
                data=item,
            )
            for item in recommendations
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
            if not (
                step.capability_id.startswith("research.")
                or step.capability_id == "collection_then_analyze"
            ):
                continue
            research_items = output.get("items", [])
            if research_items:
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:items",
                        type=(
                            "recommendation_list"
                            if "recommend" in step.capability_id
                            else "information_list"
                        ),
                        title=step.title,
                        data={"items": research_items},
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
            if output.get("trends"):
                blocks.append(
                    AgentResultBlock(
                        block_id=f"{state['turn_id']}:{step.step_id}:trends",
                        type="trend_summary",
                        title="趋势摘要",
                        data={
                            "trends": output["trends"],
                            "counterexamples": output.get(
                                "counterexamples", []
                            ),
                            "coverage_gaps": output.get(
                                "coverage_gaps", []
                            ),
                        },
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
        if source_errors:
            blocks.append(
                AgentResultBlock(
                    block_id=f"{state['turn_id']}:partial",
                    type="partial_failure",
                    title="部分来源失败",
                    data={"errors": source_errors, "retryable": True},
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
        research_steps = [
            step
            for step in plan.steps
            if step.capability_id.startswith("research.")
            or step.capability_id == "collection_then_analyze"
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
        if status == "failed":
            message = "任务未完成，请查看可定位错误。"
        elif research_steps and not recommendations:
            message = (
                f"研究部分完成，返回 {research_item_count} 条可追溯结果。"
                if status == "partial"
                else f"研究完成，返回 {research_item_count} 条可追溯结果。"
            )
        elif asset_steps:
            message = f"检索完成，返回 {asset_match_count} 条可定位片段。"
        elif status == "partial":
            message = (
                "部分完成：已保留可用来源，并推荐 "
                f"{len(recommendations)} 条信息。"
            )
        else:
            message = (
                "已完成采集、筛选和推荐，共推荐 "
                f"{len(recommendations)} 条信息。"
            )
        result = AgentTurnResult(
            status=status,
            message=message,
            plan=plan,
            result_blocks=blocks,
            business_run_ids=(
                [collection["id"]] if collection.get("id") else []
            ),
            errors=errors,
            retryable_errors=[error for error in errors if error.retryable],
        )
        return {"status": status, "result": result.model_dump(mode="json")}

    def _finalize(self, state: AgentTaskState) -> dict[str, Any]:
        return {}

    def _cancelled(self, state: AgentTaskState) -> bool:
        return bool(
            state.get("cancel_requested")
            or self.cancellation_checker(state["turn_id"])
        )
