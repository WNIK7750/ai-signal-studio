from __future__ import annotations

import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from ai_signal_api.agent_runtime.graph import WorkspaceGraphRunner
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.models import CapabilityInvocationModel, SourceConfigModel


class FakePlannerModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "workspace-fake-planner"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        plan = {
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
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content=json.dumps(plan, ensure_ascii=False))
                )
            ]
        )


def _run_graph(client):
    with client.app.state.session_factory() as session:
        executor = build_capability_executor(
            session,
            client.app.state.settings,
        )
        runner = WorkspaceGraphRunner(
            executor=executor,
            planner_model=FakePlannerModel(),
            checkpointer=InMemorySaver(),
        )
        result = runner.run(
            turn_id="turn_graph_test",
            conversation_id="conversation_graph_test",
            request_id="request_graph_test",
            message="收集最近 24 小时的 AI 信息，并从中推荐 5 条最值得看的 Agent 相关内容。",
        )
        calls = list(
            session.scalars(
                select(CapabilityInvocationModel).order_by(
                    CapabilityInvocationModel.started_at,
                    CapabilityInvocationModel.id,
                )
            )
        )
    return result, calls


def test_fake_model_uses_real_state_graph_for_collect_query_recommend(
    client,
) -> None:
    result, calls = _run_graph(client)

    assert result.status == "complete"
    assert [call.capability_id for call in calls] == [
        "collection.run.start",
        "intelligence.timeline.query",
        "intelligence.recommend",
    ]
    previews = [
        block
        for block in result.result_blocks
        if block.type == "signal_preview"
    ]
    assert 3 <= len(previews) <= 5
    assert all(block.data["information_id"].startswith("info_") for block in previews)
    assert all("/timeline?focus=info_" in block.data["app_path"] for block in previews)


def test_one_source_failure_returns_partial_with_signal_previews(client) -> None:
    with client.app.state.session_factory() as session:
        session.add(
            SourceConfigModel(
                name="故障来源",
                kind="unsupported",
                config={},
                enabled=True,
            )
        )
        session.commit()

    result, _calls = _run_graph(client)

    assert result.status == "partial"
    assert result.message != "任务未完成，请查看可定位错误。"
    assert "来源" in result.message
    assert any(
        block.type == "partial_failure" for block in result.result_blocks
    )
    assert any(
        block.type == "result_summary" for block in result.result_blocks
    )
    assert any(
        block.type == "signal_preview" for block in result.result_blocks
    )
    assert result.retryable_errors
