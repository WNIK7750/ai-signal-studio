from __future__ import annotations

import os
from pathlib import Path
import time

import pytest
from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.main import create_app


@pytest.mark.live_model
def test_workspace_agent_real_model_full_chain(tmp_path: Path) -> None:
    if os.getenv("AI_SIGNAL_RUN_LIVE_MODEL_TESTS") != "1":
        pytest.skip("live model acceptance is not authorized")

    defaults = Settings()
    settings = defaults.model_copy(
        update={
            "database_url": (
                f"sqlite:///{(tmp_path / 'live-acceptance.db').as_posix()}"
            ),
            "source_seed_mode": "demo",
            "artifact_root": tmp_path / "artifacts",
            "agent_pack_root": tmp_path / "agent-packs",
            "llm_timeout_seconds": min(
                defaults.llm_timeout_seconds,
                45,
            ),
        }
    )
    app = create_app(settings=settings, seed_demo_sources=True)
    with TestClient(app) as client:
        conversation = client.post(
            "/api/agent-conversations",
            json={"title": "真实模型完整链路验收"},
        )
        assert conversation.status_code == 201
        conversation_id = conversation.json()["id"]
        requested_live_model = os.getenv(
            "AI_SIGNAL_LIVE_MODEL_ID",
            "qwen3.7-plus",
        )
        models = client.get("/api/models").json()
        selected_model = next(
            (
                model
                for model in models
                if model["model_id"] == requested_live_model
                or model["name"] == requested_live_model
            ),
            None,
        )
        if selected_model is None:
            pytest.skip(
                f"configured live model {requested_live_model} is unavailable"
            )
        selected_model_id = selected_model["id"]
        accepted = client.post(
            f"/api/agent-conversations/{conversation_id}/turns",
            json={
                "message": (
                    "你好，请你帮我收集最近24小时的热点AI内容，"
                    "并选出其中影响力最大的三个，给我分析总结"
                ),
                "client_message_id": "live-acceptance-once",
                "model_id": selected_model_id,
            },
        )
        assert accepted.status_code == 202
        turn_id = accepted.json()["id"]

        deadline = time.monotonic() + 90
        turn = accepted.json()
        while (
            turn["status"]
            not in {"complete", "partial", "failed", "cancelled"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.25)
            response = client.get(f"/api/agent-turns/{turn_id}")
            assert response.status_code == 200
            turn = response.json()

        assert turn["status"] == "complete", turn
        assert turn["workflow_version"] == "0.8.0"
        assert turn["requested_model_id"] == selected_model_id
        assert turn["effective_model_id"] == selected_model_id
        assert turn["total_duration_ms"] >= 0
        assert turn["plan"] or turn["error"]

        stream = client.get(f"/api/agent-turns/{turn_id}/events")
        assert stream.status_code == 200
        assert "turn." in stream.text

        if turn["status"] in {"complete", "partial"}:
            blocks = turn["result"]["result_blocks"]
            referenced = [
                block
                for block in blocks
                if block["type"] in {
                    "signal_preview",
                    "recommendation_list",
                    "information_list",
                }
            ]
            assert referenced
            serialized = str(referenced)
            assert "info_" in serialized
            assert "/timeline?focus=info_" in serialized

        follow_up = client.post(
            f"/api/agent-conversations/{conversation_id}/turns",
            json={
                "message": (
                    "那么请你就目前收集的三天内的热点AI内容，"
                    "并选出其中影响力最大的三个，给我分析总结"
                ),
                "client_message_id": "live-acceptance-follow-up-once",
                "model_id": selected_model_id,
            },
        )
        assert follow_up.status_code == 202
        follow_up_turn_id = follow_up.json()["id"]
        deadline = time.monotonic() + 90
        follow_up_turn = follow_up.json()
        while (
            follow_up_turn["status"]
            not in {"complete", "partial", "failed", "cancelled"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.25)
            response = client.get(
                f"/api/agent-turns/{follow_up_turn_id}"
            )
            assert response.status_code == 200
            follow_up_turn = response.json()

        assert follow_up_turn["status"] == "complete", follow_up_turn
        assert follow_up_turn["requested_model_id"] == selected_model_id
        assert follow_up_turn["effective_model_id"] == selected_model_id
        follow_up_goal = follow_up_turn["result"]["goal"]
        assert follow_up_goal["operation_mode"] == "analyze_existing"
        assert follow_up_goal["time_window"]["lookback_hours"] == 72
        assert follow_up_goal["max_items"] == 3
        capabilities = [
            step["capability_id"]
            for step in follow_up_turn["plan"]["steps"]
        ]
        assert capabilities == [
            "intelligence.search",
            "research.recommend",
            "research.trend_brief",
        ]
        follow_up_blocks = follow_up_turn["result"]["result_blocks"]
        follow_up_references = [
            block
            for block in follow_up_blocks
            if block["type"] in {
                "signal_preview",
                "recommendation_list",
                "information_list",
            }
        ]
        assert follow_up_references
        follow_up_serialized = str(follow_up_references)
        assert "info_" in follow_up_serialized
        assert "/timeline?focus=info_" in follow_up_serialized

        contextual = client.post(
            f"/api/agent-conversations/{conversation_id}/turns",
            json={
                "message": (
                    "请你挑选出刚才收集内容中，"
                    "影响力最大的三个并进行分析总结"
                ),
                "client_message_id": "live-contextual-reasoning-once",
                "model_id": selected_model_id,
            },
        )
        assert contextual.status_code == 202
        contextual_turn_id = contextual.json()["id"]
        deadline = time.monotonic() + 90
        contextual_turn = contextual.json()
        while (
            contextual_turn["status"]
            not in {"complete", "partial", "failed", "cancelled"}
            and time.monotonic() < deadline
        ):
            time.sleep(0.25)
            response = client.get(
                f"/api/agent-turns/{contextual_turn_id}"
            )
            assert response.status_code == 200
            contextual_turn = response.json()

        assert contextual_turn["status"] == "complete", contextual_turn
        assert contextual_turn["requested_model_id"] == selected_model_id
        assert contextual_turn["effective_model_id"] == selected_model_id
        contextual_steps = contextual_turn["plan"]["steps"]
        assert len(contextual_steps) == 1
        assert contextual_steps[0]["kind"] == "model_reasoning"
        assert contextual_steps[0]["capability_id"] is None
        model_response = next(
            block
            for block in contextual_turn["result"]["result_blocks"]
            if block["type"] == "model_response"
        )
        assert model_response["data"]["content"]
        assert (
            model_response["data"]["basis"]
            == "conversation_context"
        )
        assert (
            model_response["data"]["effective_model_id"]
            == selected_model_id
        )
