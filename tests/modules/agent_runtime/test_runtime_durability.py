from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import ValidationError

from ai_signal_api.agent_runtime.contracts import AgentPlan
from ai_signal_api.agent_runtime.graph import WorkspaceGraphRunner
from ai_signal_api.agent_runtime.harness import RecoveryScanner
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.models import AgentTurnModel


def _plan(*, clarification: bool = False, approval: bool = False) -> dict[str, Any]:
    return {
        "objective": "执行受控研究",
        "constraints": {
            "requires_clarification": clarification,
            "clarification_question": "需要查询哪个主题？",
        },
        "assumptions": [],
        "planning_mode": "dynamic",
        "selected_domains": ["intelligence"],
        "steps": [
            {
                "step_id": "query",
                "title": "查询信息",
                "goal": "查询已保存信息",
                "kind": "capability",
                "domains": ["intelligence"],
                "capability_id": "intelligence.timeline.query",
                "arguments": {"limit": 3},
                "dependencies": [],
                "success_criteria": "返回可引用信息",
                "acceptance_policy": {
                    "id": "information_results.v1",
                    "params": {"min_items": 0},
                },
                "side_effect": "read",
                "risk": "medium" if approval else "low",
                "failure_policy": "continue_independent",
            }
        ],
        "max_replans": 2,
    }


class PlanModel(BaseChatModel):
    plan: dict[str, Any]

    @property
    def _llm_type(self) -> str:
        return "durability-plan-model"

    def _generate(
        self,
        messages,
        stop=None,
        run_manager=None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=json.dumps(self.plan, ensure_ascii=False)
                    )
                )
            ]
        )


def _runner(client, plan: dict[str, Any]) -> WorkspaceGraphRunner:
    session = client.app.state.session_factory()
    runner = WorkspaceGraphRunner(
        executor=build_capability_executor(
            session,
            client.app.state.settings,
        ),
        planner_model=PlanModel(plan=plan),
        checkpointer=InMemorySaver(),
    )
    runner._test_session = session
    return runner


def test_agent_plan_accepts_valid_forward_dependency_and_rejects_cycle() -> None:
    valid = _plan()
    valid["steps"] = [
        {
            **valid["steps"][0],
            "step_id": "second",
            "dependencies": ["first"],
        },
        {
            **valid["steps"][0],
            "step_id": "first",
            "dependencies": [],
        },
    ]
    assert AgentPlan.model_validate(valid).steps[0].dependencies == ["first"]

    cyclic = _plan()
    cyclic["steps"] = [
        {
            **cyclic["steps"][0],
            "step_id": "first",
            "dependencies": ["second"],
        },
        {
            **cyclic["steps"][0],
            "step_id": "second",
            "dependencies": ["first"],
        },
    ]
    try:
        AgentPlan.model_validate(cyclic)
    except ValidationError as error:
        assert "AGENT_PLAN_DEPENDENCY_CYCLE" in str(error)
    else:
        raise AssertionError("cyclic plan should be rejected")


def test_clarification_interrupt_resumes_same_thread(client) -> None:
    runner = _runner(client, _plan(clarification=True))
    try:
        waiting = runner.advance(
            turn_id="turn_clarify",
            conversation_id="conversation_clarify",
            request_id="request_clarify",
            message="帮我研究",
        )
        assert waiting["status"] == "waiting_input"
        assert waiting["interrupt"]["kind"] == "clarification"

        completed = runner.resume(
            turn_id="turn_clarify",
            payload={"answer": "Agent"},
        )
        assert completed["result"]["status"] == "complete"
    finally:
        runner._test_session.close()


def test_approval_interrupt_rejects_without_executing_capability(client) -> None:
    runner = _runner(client, _plan(approval=True))
    try:
        waiting = runner.advance(
            turn_id="turn_approval",
            conversation_id="conversation_approval",
            request_id="request_approval",
            message="执行受控查询",
        )
        assert waiting["status"] == "waiting_approval"
        assert waiting["interrupt"]["kind"] == "approval"

        completed = runner.resume(
            turn_id="turn_approval",
            payload={"approved": False},
        )
        assert completed["result"]["status"] == "partial"
        assert completed["result"]["errors"][0]["code"] == "APPROVAL_REJECTED"
    finally:
        runner._test_session.close()


def test_recovery_scanner_requeues_only_expired_running_turn(client) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    created = client.post(
        f"/api/agent-conversations/{conversation['id']}/turns",
        json={
            "message": "收集并推荐 Agent 信息",
            "client_message_id": "recovery-scan",
        },
    ).json()
    with client.app.state.session_factory() as session:
        turn = session.get(AgentTurnModel, created["id"])
        turn.status = "running"
        turn.lease_owner = "dead-worker"
        turn.lease_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

        recovered = RecoveryScanner(session).scan()

        assert recovered == [turn.id]
        assert turn.status == "queued"
        assert turn.lease_owner is None


def test_cancellation_checker_stops_before_next_step(client) -> None:
    checks = iter([False, False, True])
    runner = _runner(client, _plan())
    runner.cancellation_checker = lambda _turn_id: next(checks, True)
    try:
        result = runner.run(
            turn_id="turn_cancel_boundary",
            conversation_id="conversation_cancel_boundary",
            request_id="request_cancel_boundary",
            message="执行查询",
        )
        assert result.status == "cancelled"
    finally:
        runner._test_session.close()
