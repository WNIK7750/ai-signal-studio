from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from ai_signal_api.agent_runtime.contracts import (
    AgentGoalSpec,
    AgentPlan,
    AgentPlanningOutput,
    ExecutionManifest,
    PlanStep,
    validate_goal_plan_coverage,
)
from ai_signal_api.agent_runtime.graph import WorkspaceGraphRunner
from ai_signal_api.agent_runtime.harness import build_planner_model
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.config import Settings
from ai_signal_api.models import CapabilityInvocationModel
from ai_signal_api.modules.models.service import (
    ModelSelection,
    ResolvedModel,
)
from ai_signal_api.modules.intelligence.agent.schemas import (
    RecommendationDecision,
    TrendFinding,
    TrendSynthesis,
)


ORIGINAL_COLLECT_PROMPT = (
    "你好，请你帮我收集最近24小时的热点AI内容，并选出其中影响力最大的三个，给我分析总结"
)
ORIGINAL_EXISTING_PROMPT = (
    "那么请你就目前收集的三天内的热点AI内容，并选出其中影响力最大的三个，给我分析总结"
)


def _goal(*, mode: str, hours: int, collect: bool) -> dict:
    return {
        "operation_mode": mode,
        "topic": "AI",
        "time_window": {"lookback_hours": hours},
        "max_items": 3,
        "ranking_criterion": "impact",
        "deliverables": ["recommendations", "trend_summary", "evidence"],
        "use_existing": True,
        "requires_collection": collect,
        "requires_synthesis": True,
    }


def _plan(*, collect: bool, hours: int) -> dict:
    steps = []
    dependency: list[str] = []
    if collect:
        steps.append(
            {
                "step_id": "collect",
                "title": "采集热点信息",
                "goal": "采集启用来源并保留去重结果",
                "kind": "capability",
                "domains": ["collection"],
                "capability_id": "collection.run.start",
                "dependencies": [],
                "success_criteria": "采集运行完成；新增为零也继续",
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
        dependency = ["collect"]
    steps.extend(
        [
            {
                "step_id": "search",
                "title": "统一检索时间窗口",
                "goal": f"跨阶段检索最近 {hours} 小时内的信息",
                "kind": "capability",
                "domains": ["intelligence"],
                "capability_id": "intelligence.search",
                "arguments": {
                    "query": "AI",
                    "scopes": ["intelligence"],
                    "limit": 50,
                },
                "dependencies": dependency,
                "success_criteria": "只返回窗口内真实信息 ID",
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
                        "goal": "本地候选不足时搜索并缓存网页",
                        "kind": "capability",
                        "domains": ["collection"],
                        "capability_id": "web.search.collect",
                        "arguments": {
                            "query": "AI 最新动态",
                            "limit": 6,
                            "freshness": "pd",
                        },
                        "dependencies": ["search"],
                        "success_criteria": "补证成功或明确说明跳过原因",
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
                "title": "按影响力选出三条",
                "goal": "使用可解释的工作区信号排序",
                "kind": "domain_agent",
                "domains": ["intelligence"],
                "capability_id": "research.recommend",
                "arguments": {
                    "topic": "AI",
                    "lookback_hours": hours,
                    "limit": 3,
                    "rank_by": "impact",
                },
                "dependencies": [
                    "web_search" if collect else "search"
                ],
                "success_criteria": "最多三条，均有来源、理由和站内深链",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 1, "max_items": 3},
                },
                "side_effect": "read",
                "risk": "low",
                "failure_policy": "stop_dependents",
                "satisfies": ["recommendations", "evidence"],
            },
            {
                "step_id": "synthesize",
                "title": "综合分析",
                "goal": "基于三条入选信息形成跨信息分析",
                "kind": "domain_agent",
                "domains": ["intelligence"],
                "capability_id": "research.trend_brief",
                "arguments": {
                    "topic": "AI",
                    "lookback_hours": hours,
                    "limit": 3,
                    "rank_by": "impact",
                    "output_max_chars": 1600,
                },
                "dependencies": ["recommend"],
                "success_criteria": "每个 finding 引用真实 information_id",
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
        "objective": "选出时间范围内影响力最大的三条 AI 内容并综合分析",
        "constraints": {
            "lookback_hours": hours,
            "max_items": 3,
            "ranking_criterion": "impact",
        },
        "assumptions": [],
        "planning_mode": "dynamic",
        "selected_domains": ["collection", "intelligence"]
        if collect
        else ["intelligence"],
        "steps": steps,
        "max_replans": 2,
    }


@pytest.mark.parametrize(
    ("prompt", "goal"),
    [
        (
            ORIGINAL_COLLECT_PROMPT,
            _goal(mode="collect_then_analyze", hours=24, collect=True),
        ),
        (
            ORIGINAL_EXISTING_PROMPT,
            _goal(mode="analyze_existing", hours=72, collect=False),
        ),
    ],
)
def test_original_prompts_have_explicit_goal_and_fully_covered_plan(
    prompt: str,
    goal: dict,
) -> None:
    planning = AgentPlanningOutput.model_validate(
        {
            "goal": goal,
            "plan": _plan(
                collect=goal["requires_collection"],
                hours=goal["time_window"]["lookback_hours"],
            ),
        }
    )

    assert prompt in {ORIGINAL_COLLECT_PROMPT, ORIGINAL_EXISTING_PROMPT}
    assert planning.goal.max_items == 3
    assert planning.goal.ranking_criterion == "impact"
    assert planning.goal.requires_synthesis is True
    assert validate_goal_plan_coverage(planning.goal, planning.plan) == []


def test_server_contract_overrides_model_owned_web_search_risk() -> None:
    model_plan = _plan(collect=True, hours=24)
    model_plan["constraints"] = {
        "time_window_hours": 24,
        "max_results": 3,
        "ranking": "impact",
    }
    web_step = next(
        step
        for step in model_plan["steps"]
        if step["capability_id"] == "web.search.collect"
    )
    web_step["risk"] = "medium"
    recommendation_step = next(
        step
        for step in model_plan["steps"]
        if step["capability_id"] == "research.recommend"
    )
    recommendation_step["domains"] = ["research"]

    normalized = WorkspaceGraphRunner._apply_server_planning_contracts(
        AgentPlan.model_validate(model_plan),
        AgentGoalSpec.model_validate(
            _goal(mode="collect_then_analyze", hours=24, collect=True)
        ),
    )
    normalized_web_step = next(
        step
        for step in normalized.steps
        if step.capability_id == "web.search.collect"
    )

    assert normalized_web_step.risk == "low"
    assert normalized_web_step.side_effect == "external"
    assert normalized_web_step.acceptance_policy.id == "capability_effect.v1"
    assert normalized.constraints["lookback_hours"] == 24
    assert normalized.constraints["max_items"] == 3
    assert normalized.constraints["ranking_criterion"] == "impact"
    recommendation_step = next(
        step
        for step in normalized.steps
        if step.capability_id == "research.recommend"
    )
    assert recommendation_step.domains == ["intelligence"]
    assert recommendation_step.arguments["lookback_hours"] == 24
    assert recommendation_step.arguments["limit"] == 3
    assert recommendation_step.arguments["rank_by"] == "impact"
    assert normalized.selected_domains == ["collection", "intelligence"]


def test_incomplete_collection_only_plan_is_rejected_with_actionable_gaps() -> None:
    complete = _plan(collect=True, hours=24)
    incomplete = deepcopy(complete)
    incomplete["steps"] = incomplete["steps"][:1]

    goal = AgentGoalSpec.model_validate(
        _goal(mode="collect_then_analyze", hours=24, collect=True)
    )
    gaps = validate_goal_plan_coverage(
        goal,
        AgentPlanningOutput.model_validate(
            {"goal": goal, "plan": incomplete}
        ).plan,
    )

    assert "missing_capability:intelligence.search" in gaps
    assert "missing_capability:web.search.collect" in gaps
    assert "missing_capability:research.recommend" in gaps
    assert "missing_capability:research.trend_brief" in gaps
    assert "uncovered_deliverable:trend_summary" in gaps


def test_research_plan_requires_the_exact_capability_dependency_chain() -> None:
    planning = AgentPlanningOutput.model_validate(
        {
            "goal": _goal(
                mode="collect_then_analyze",
                hours=24,
                collect=True,
            ),
            "plan": _plan(collect=True, hours=24),
        }
    )
    broken = planning.plan.model_copy(deep=True)
    broken.steps[3].dependencies = []

    gaps = validate_goal_plan_coverage(planning.goal, broken)

    assert (
        "missing_dependency:research.recommend:"
        "web.search.collect"
    ) in gaps


def test_execution_manifest_uses_0_6_schema_versions_and_model_trace() -> None:
    manifest = ExecutionManifest(
        requested_model_id="model-requested",
        effective_model_id="model-effective",
        model_config_ref="model-requested",
        capability_snapshot_digest="digest",
    )

    assert manifest.workflow_version == "0.8.0"
    assert manifest.state_schema_version == "1.2.0"
    assert manifest.plan_schema_version == "1.2.0"
    assert manifest.event_schema_version == "1.2.0"
    assert manifest.requested_model_id == "model-requested"
    assert manifest.effective_model_id == "model-effective"


def test_dashscope_profile_is_isolated_from_agent_graph() -> None:
    model = ResolvedModel(
        id="model-qwen",
        name="qwen3.7-flash",
        provider="openai_compatible",
        provider_id="provider-qwen",
        provider_name="阿里云百炼",
        model_id="qwen3.7-flash",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="test-only",
        supports_vision=False,
        output_token_limit=None,
        enabled=True,
        is_default=True,
    )

    class ModelService:
        def select_for_request(self, _model_id: str | None) -> ModelSelection:
            return ModelSelection(model.id, model)

    planner, effective_id = build_planner_model(
        Settings(_env_file=None),
        ModelService(),  # type: ignore[arg-type]
        model.id,
    )

    assert effective_id == model.id
    assert getattr(planner, "extra_body") == {"enable_thinking": False}
    assert planner.metadata["structured_output_method"] == "function_calling"
    assert (
        planner.metadata["provider_family"]
        == "dashscope-openai-compatible"
    )


class QueuePlanningModel(BaseChatModel):
    responses: list[Any]
    calls: int = 0
    system_prompts: list[str] = []
    enable_research_synthesis: bool = False

    @property
    def _llm_type(self) -> str:
        return "queue-planning-model"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        self.system_prompts.append(str(messages[0].content))
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        response = self.responses[index]
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=(
                            json.dumps(response, ensure_ascii=False)
                            if isinstance(response, dict)
                            else str(response)
                        )
                    )
                )
            ]
        )


def _model_reasoning_plan() -> dict[str, Any]:
    return {
        "objective": "基于当前会话中已有内容完成分析总结",
        "constraints": {
            "lookback_hours": 72,
            "max_items": 3,
            "ranking_criterion": "impact",
        },
        "assumptions": [
            "只使用当前会话中已出现的内容，不把模型常识伪装成工作区证据"
        ],
        "planning_mode": "dynamic",
        "selected_domains": ["intelligence"],
        "steps": [
            {
                "step_id": "reason",
                "title": "基于会话语境分析",
                "goal": "挑选会话已有内容中影响力最大的三个并总结",
                "kind": "model_reasoning",
                "domains": ["intelligence"],
                "capability_id": None,
                "arguments": {
                    "response_basis": "conversation_context",
                    "output_max_chars": 1600,
                },
                "dependencies": [],
                "success_criteria": "给出有证据边界的直接回答",
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
    }


def test_model_reasoning_step_does_not_require_a_capability() -> None:
    step = PlanStep.model_validate(_model_reasoning_plan()["steps"][0])

    assert step.kind == "model_reasoning"
    assert step.capability_id is None

    invalid = deepcopy(_model_reasoning_plan()["steps"][0])
    invalid["kind"] = "capability"
    with pytest.raises(ValueError, match="AGENT_PLAN_CAPABILITY_REQUIRED"):
        PlanStep.model_validate(invalid)


def test_contextual_follow_up_can_use_selected_model_without_tool_call(
    client,
) -> None:
    goal = {
        "operation_mode": "direct",
        "topic": "AI",
        "time_window": {"lookback_hours": 72},
        "max_items": 3,
        "ranking_criterion": "impact",
        "deliverables": ["model_response"],
        "use_existing": True,
        "requires_collection": False,
        "requires_synthesis": True,
    }
    model = QueuePlanningModel(
        responses=[
            {"goal": goal, "plan": _model_reasoning_plan()},
            (
                "从当前会话里可见的三项内容看，第一项影响产品交付，"
                "第二项影响开发者生态，第三项影响推理成本。"
                "这份判断只依据会话摘要，不代表站内信息库的实时排名。"
            ),
        ]
    )
    with client.app.state.session_factory() as session:
        executor = build_capability_executor(
            session,
            client.app.state.settings,
        )
        invocation_count = session.query(CapabilityInvocationModel).count()
        runner = WorkspaceGraphRunner(
            executor=executor,
            planner_model=model,
            synthesis_model=model,
            checkpointer=InMemorySaver(),
        )
        result = runner.run(
            turn_id="turn_contextual_reasoning",
            conversation_id="conversation_contextual_reasoning",
            request_id="request_contextual_reasoning",
            message="请你挑选出刚才收集内容中，影响力最大的三个并进行分析总结",
            conversation_context={
                "recent_messages": [
                    {
                        "role": "assistant",
                        "summary": (
                            "已收集：AI 产品发布；开发者工具更新；"
                            "推理模型成本变化。"
                        ),
                        "turn_id": "turn_previous",
                    }
                ],
                "prior_turn_refs": [
                    {
                        "turn_id": "turn_previous",
                        "result_summaries": [
                            {
                                "type": "recommendation_list",
                                "data": {
                                    "items": [
                                        {
                                            "information_id": "info_previous_1",
                                            "title": "AI 产品发布",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            },
            effective_model_id="selected-real-model",
        )
        assert (
            session.query(CapabilityInvocationModel).count()
            == invocation_count
        )

    assert model.calls == 2
    assert result.status == "complete"
    assert result.plan.steps[0].kind == "model_reasoning"
    assert result.plan.steps[0].capability_id is None
    response = next(
        block
        for block in result.result_blocks
        if block.type == "model_response"
    )
    assert "只依据会话摘要" in response.data["content"]
    assert response.data["basis"] == "conversation_context"
    assert response.data["effective_model_id"] == "selected-real-model"
    assert response.data["information_ids"] == ["info_previous_1"]


def test_empty_timeline_still_runs_model_backed_recommendation_and_trend(
    client,
) -> None:
    goal = _goal(mode="collect_then_analyze", hours=24, collect=True)
    future_from = datetime.now(timezone.utc) + timedelta(days=30)
    future_to = future_from + timedelta(hours=24)
    goal["time_window"] = {
        "lookback_hours": 24,
        "published_from": future_from.isoformat(),
        "published_to": future_to.isoformat(),
    }
    plan = _plan(collect=True, hours=24)
    plan["steps"][3]["kind"] = "domain_agent"
    analysis = {
        "recommendation_overview": (
            "当前时间窗口没有可核验候选，不能编造热点推荐。"
        ),
        "recommendations": [],
        "uncertainties": ["需要补充时间窗口内的来源证据。"],
        "trend": {
            "overview": (
                "当前证据不足以判断最近 24 小时的 AI 趋势；"
                "已完成分析但不生成无引用结论。"
            ),
            "key_findings": [],
            "why_it_matters": [],
            "differences": [],
            "uncertainties": ["时间窗口内没有可引用信息。"],
            "information_ids": [],
            "synthesis_mode": "model",
        },
    }
    model = QueuePlanningModel(
        responses=[{"goal": goal, "plan": plan}, analysis],
        enable_research_synthesis=True,
    )
    events: list[tuple[str, dict[str, Any], str | None]] = []
    request_id = "request_empty_research_model"
    with client.app.state.session_factory() as session:
        runner = WorkspaceGraphRunner(
            executor=build_capability_executor(
                session,
                client.app.state.settings,
            ),
            planner_model=model,
            synthesis_model=model,
            checkpointer=InMemorySaver(),
            event_sink=lambda event_type, data, step_id: events.append(
                (event_type, data, step_id)
            ),
        )
        result = runner.run(
            turn_id="turn_empty_research_model",
            conversation_id="conversation_empty_research_model",
            request_id=request_id,
            message=ORIGINAL_COLLECT_PROMPT,
            effective_model_id="selected-research-model",
        )
        capability_ids = [
            item.capability_id
            for item in session.query(CapabilityInvocationModel)
            .filter(CapabilityInvocationModel.request_id == request_id)
            .order_by(CapabilityInvocationModel.started_at)
            .all()
        ]

    assert model.calls == 2
    assert capability_ids == [
        "collection.run.start",
        "intelligence.search",
        "web.search.collect",
        "research.recommend",
        "research.trend_brief",
    ]
    assert result.status == "partial"
    assert {
        step_id: data["status"]
        for event_type, data, step_id in events
        if event_type == "step.outcome"
        } == {
            "collect": "completed",
            "search": "partial",
            "web_search": "partial",
            "recommend": "partial",
            "synthesize": "partial",
        }
    blocks = {block.type: block for block in result.result_blocks}
    assert blocks["recommendation_list"].data["items"] == []
    assert (
        blocks["recommendation_list"].data["analysis_mode"] == "model"
    )
    assert (
        blocks["trend_summary"].data["synthesis_mode"] == "model"
    )
    assert "证据不足" in blocks["trend_summary"].data["overview"]
    assert "partial_failure" in blocks


def test_research_structured_output_accepts_fenced_provider_json() -> None:
    decoded = WorkspaceGraphRunner._decode_structured_content(
        "说明如下：\n```json\n"
        '{"recommendations":[],"trend":{"overview":"证据不足"}}'
        "\n```"
    )

    assert decoded["recommendations"] == []
    assert decoded["trend"]["overview"] == "证据不足"


def test_structured_output_accepts_openai_compatible_tool_call_arguments() -> None:
    raw = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "call_research",
                    "type": "function",
                    "function": {
                        "name": "ResearchAnalysisSynthesis",
                        "arguments": (
                            '{"recommendations":[],"trend":'
                            '{"overview":"证据不足"}}'
                        ),
                    },
                }
            ]
        },
    )

    decoded = WorkspaceGraphRunner._decode_structured_raw(raw)

    assert decoded["recommendations"] == []
    assert decoded["trend"]["overview"] == "证据不足"


def test_generated_analysis_defaults_to_chinese_without_rewriting_sources() -> None:
    assert (
        WorkspaceGraphRunner._prefer_chinese_generated_text(
            "No candidates were supplied for analysis.",
            "当前没有可分析的候选信息。",
        )
        == "当前没有可分析的候选信息。"
    )
    assert (
        WorkspaceGraphRunner._prefer_chinese_generated_text(
            "模型已基于三条证据完成分析。",
            "后备说明",
        )
        == "模型已基于三条证据完成分析。"
    )


def test_research_trend_citations_are_grounded_to_real_information_ids() -> None:
    trend = TrendSynthesis(
        overview="模型生成的趋势判断",
        key_findings=[
            TrendFinding(
                title="趋势",
                summary="模型引用了不存在的证据。",
                information_ids=["invented_id"],
            )
        ],
        why_it_matters=[],
        differences=[],
        uncertainties=[],
        information_ids=["invented_id", "info_2"],
        synthesis_mode="model",
    )

    grounded, repaired = WorkspaceGraphRunner._ground_trend_synthesis(
        trend,
        ["info_1", "info_2"],
    )

    assert repaired is True
    assert grounded.information_ids == ["info_2"]
    assert grounded.key_findings[0].information_ids == [
        "info_1",
        "info_2",
    ]
    assert grounded.synthesis_mode == "model"


def test_research_trend_drops_findings_when_no_evidence_exists() -> None:
    trend = TrendSynthesis(
        overview="没有可验证证据",
        key_findings=[
            TrendFinding(
                title="无法验证",
                summary="不能保留无依据的判断。",
                information_ids=["invented_id"],
            )
        ],
        information_ids=["invented_id"],
        synthesis_mode="model",
    )

    grounded, repaired = WorkspaceGraphRunner._ground_trend_synthesis(
        trend,
        [],
    )

    assert repaired is True
    assert grounded.information_ids == []
    assert grounded.key_findings == []


def test_research_selection_keeps_model_reasoning_and_fills_real_candidates() -> None:
    candidates = [
        {
            "information_id": "info_1",
            "reason": "能力排序理由 1",
            "ranking_basis": ["可信来源"],
        },
        {
            "information_id": "info_2",
            "reason": "能力排序理由 2",
            "ranking_basis": ["高相关度"],
        },
        {
            "information_id": "info_3",
            "reason": "能力排序理由 3",
            "ranking_basis": ["近期发布"],
        },
    ]
    decisions = [
        RecommendationDecision(
            information_id="info_1",
            reason="模型判断理由",
            priority="important",
            tags=["智能体", "工作流"],
        ),
        RecommendationDecision(
            information_id="invented_id",
            reason="无效引用",
        ),
    ]

    selected, repaired, model_selected_count = (
        WorkspaceGraphRunner._ground_recommendation_decisions(
            candidates,
            decisions,
            3,
        )
    )

    assert repaired is True
    assert model_selected_count == 1
    assert [item["information_id"] for item in selected] == [
        "info_1",
        "info_2",
        "info_3",
    ]
    assert selected[0]["reason"] == "模型判断理由"
    assert selected[0]["color"] == "important"
    assert selected[0]["tags"] == ["智能体", "工作流"]
    assert selected[1]["reason"] == "能力排序理由 2"
    assert "真实排序补齐" in selected[1]["ranking_basis"][-1]


def test_research_model_failure_keeps_chinese_deterministic_result_summary(
    client,
) -> None:
    goal = _goal(mode="collect_then_analyze", hours=24, collect=True)
    model = QueuePlanningModel(
        responses=[
            {"goal": goal, "plan": _plan(collect=True, hours=24)},
            "not-json",
        ],
        enable_research_synthesis=True,
    )
    with client.app.state.session_factory() as session:
        runner = WorkspaceGraphRunner(
            executor=build_capability_executor(
                session,
                client.app.state.settings,
            ),
            planner_model=model,
            synthesis_model=model,
            checkpointer=InMemorySaver(),
        )
        result = runner.run(
            turn_id="turn_research_provider_fallback",
            conversation_id="conversation_research_provider_fallback",
            request_id="request_research_provider_fallback",
            message=ORIGINAL_COLLECT_PROMPT,
            effective_model_id="selected-research-model",
        )

    blocks = {block.type: block for block in result.result_blocks}
    assert result.status == "partial"
    assert blocks["recommendation_list"].data["items"]
    assert (
        blocks["recommendation_list"].data["analysis_mode"]
        == "deterministic_fallback"
    )
    summary = blocks["result_summary"]
    assert "JSON 格式无效或被截断" in str(
        summary.data["errors"]
    )
    assert "任务未完成，请查看可定位错误" not in result.message


def test_graph_rejects_incomplete_plan_then_replans_once_with_feedback(
    client,
) -> None:
    goal = _goal(mode="collect_then_analyze", hours=24, collect=True)
    complete = _plan(collect=True, hours=24)
    incomplete = deepcopy(complete)
    incomplete["steps"] = incomplete["steps"][:1]
    model = QueuePlanningModel(
        responses=[
            {"goal": goal, "plan": incomplete},
            {"goal": goal, "plan": complete},
        ]
    )
    with client.app.state.session_factory() as session:
        runner = WorkspaceGraphRunner(
            executor=build_capability_executor(
                session,
                client.app.state.settings,
            ),
            planner_model=model,
            checkpointer=InMemorySaver(),
        )
        result = runner.run(
            turn_id="turn_goal_replan",
            conversation_id="conversation_goal_replan",
            request_id="request_goal_replan",
            message=ORIGINAL_COLLECT_PROMPT,
            effective_model_id="scripted-planner",
        )

    assert model.calls == 2
    assert "research.trend_brief" in model.system_prompts[0]
    assert "capability_effect.v1" in model.system_prompts[0]
    assert "AGENT_PLAN_COVERAGE_INCOMPLETE" in model.system_prompts[1]
    assert result.status == "complete"
    assert [
        step.capability_id for step in result.plan.steps
    ] == [
        "collection.run.start",
        "intelligence.search",
        "web.search.collect",
        "research.recommend",
        "research.trend_brief",
    ]


def test_graph_normalizes_server_owned_capability_contract_without_replan(
    client,
) -> None:
    goal = _goal(mode="collect_then_analyze", hours=24, collect=True)
    complete = _plan(collect=True, hours=24)
    mismatched = deepcopy(complete)
    mismatched["steps"][0]["acceptance_policy"] = {
        "id": "information_results.v1",
        "params": {"min_items": 3},
    }
    model = QueuePlanningModel(
        responses=[
            {"goal": goal, "plan": mismatched},
            {"goal": goal, "plan": complete},
        ]
    )
    with client.app.state.session_factory() as session:
        runner = WorkspaceGraphRunner(
            executor=build_capability_executor(
                session,
                client.app.state.settings,
            ),
            planner_model=model,
            checkpointer=InMemorySaver(),
        )
        result = runner.run(
            turn_id="turn_contract_replan",
            conversation_id="conversation_contract_replan",
            request_id="request_contract_replan",
            message=ORIGINAL_COLLECT_PROMPT,
            effective_model_id="scripted-planner",
        )

    assert model.calls == 1
    collect_step = next(
        step
        for step in result.plan.steps
        if step.capability_id == "collection.run.start"
    )
    assert collect_step.acceptance_policy.id == "capability_effect.v1"
    assert result.status == "complete"


def test_plan_schema_rejects_model_invented_capability_before_execution() -> None:
    invented = _plan(collect=True, hours=24)
    invented["steps"][0]["capability_id"] = "web_search_latest"

    with pytest.raises(ValueError, match="web_search_latest"):
        AgentPlanningOutput.model_validate(
            {
                "goal": _goal(
                    mode="collect_then_analyze",
                    hours=24,
                    collect=True,
                ),
                "plan": invented,
            }
        )
