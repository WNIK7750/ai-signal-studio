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
        accepted = client.post(
            f"/api/agent-conversations/{conversation_id}/turns",
            json={
                "message": (
                    "推荐过去 30 天最值得关注的 3 条 Agent 信息，"
                    "每条必须带站内引用。"
                ),
                "client_message_id": "live-acceptance-once",
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

        assert turn["status"] in {"complete", "partial", "failed"}
        assert turn["workflow_version"] == "0.4.0"
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
