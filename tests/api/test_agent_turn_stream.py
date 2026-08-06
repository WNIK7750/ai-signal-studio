from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ai_signal_api.models import (
    AgentMessageModel,
    AgentTurnEventModel,
    CollectionRunModel,
    SourceConfigModel,
)


def _create_turn(client: TestClient, conversation_id: str, client_id: str):
    return client.post(
        f"/api/agent-conversations/{conversation_id}/turns",
        json={
            "message": (
                "收集最近 24 小时的 AI 信息，并从中推荐 5 条最值得看的 "
                "Agent 相关内容。"
            ),
            "client_message_id": client_id,
        },
    )


def _sse_events(response) -> list[dict]:
    events: list[dict] = []
    current: dict[str, object] = {}
    for line in response.text.splitlines():
        if line.startswith("id:"):
            current["id"] = int(line.removeprefix("id:").strip())
        elif line.startswith("event:"):
            current["event"] = line.removeprefix("event:").strip()
        elif line.startswith("data:"):
            current["data"] = json.loads(line.removeprefix("data:").strip())
        elif not line and current:
            events.append(current)
            current = {}
    if current:
        events.append(current)
    return events


def test_turn_returns_202_persists_ordered_events_and_resumes_by_event_id(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()

    created = _create_turn(client, conversation["id"], "stream-message-1")

    assert created.status_code == 202
    turn = created.json()
    assert turn["status"] in {"queued", "running", "complete", "partial"}
    events = _sse_events(
        client.get(f"/api/agent-turns/{turn['id']}/events")
    )
    sequences = [event["id"] for event in events]
    assert sequences == sorted(sequences)
    assert sequences == list(range(1, len(sequences) + 1))
    assert events[0]["event"] == "turn.created"
    assert events[-1]["event"] in {
        "turn.completed",
        "turn.partial",
        "turn.failed",
    }
    assert all(
        events[index]["data"]["elapsed_ms"]
        <= events[index + 1]["data"]["elapsed_ms"]
        for index in range(len(events) - 1)
    )

    resumed = _sse_events(
        client.get(
            f"/api/agent-turns/{turn['id']}/events",
            headers={"Last-Event-ID": "3"},
        )
    )
    assert resumed
    assert all(event["id"] > 3 for event in resumed)

    persisted = client.get(f"/api/agent-turns/{turn['id']}").json()
    assert persisted["status"] in {"complete", "partial"}, persisted.get(
        "error"
    )
    assert persisted["result"]["result_blocks"]
    detail = client.get(
        f"/api/agent-conversations/{conversation['id']}"
    ).json()
    assert detail["active_turn_id"] is None
    assert detail["messages"][-1]["turn_id"] == turn["id"]


def test_duplicate_client_message_id_reuses_turn_and_side_effects(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()

    first = _create_turn(client, conversation["id"], "stream-idempotent")
    invocation_count = len(client.get("/api/capability-invocations").json())
    second = _create_turn(client, conversation["id"], "stream-idempotent")

    assert first.status_code == second.status_code == 202
    assert second.json()["id"] == first.json()["id"]
    assert len(client.get("/api/capability-invocations").json()) == invocation_count


def test_partial_turn_resume_retries_only_failed_sources(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as session:
        failed_source = SourceConfigModel(
            name="待重试故障来源",
            kind="unsupported",
            config={},
            enabled=True,
        )
        session.add(failed_source)
        session.commit()
        failed_source_id = failed_source.id

    conversation = client.post("/api/agent-conversations", json={}).json()
    turn = _create_turn(
        client,
        conversation["id"],
        "stream-partial-retry",
    ).json()
    client.get(f"/api/agent-turns/{turn['id']}/events")
    turn = client.get(f"/api/agent-turns/{turn['id']}").json()
    assert turn["status"] == "partial"

    resumed = client.post(
        f"/api/agent-turns/{turn['id']}/resume"
    )
    assert resumed.status_code == 202
    client.get(f"/api/agent-turns/{turn['id']}/events")
    assert (
        client.get(f"/api/agent-turns/{turn['id']}").json()["status"]
        == "partial"
    )

    with client.app.state.session_factory() as session:
        runs = list(
            session.scalars(
                select(CollectionRunModel).order_by(
                    CollectionRunModel.created_at
                )
            )
        )
        assert runs[-1].trigger_type == "retry"
        assert runs[-1].source_ids == [failed_source_id]
        assert (
            session.scalar(
                select(func.count(AgentMessageModel.id)).where(
                    AgentMessageModel.turn_id == turn["id"],
                    AgentMessageModel.role == "assistant",
                )
            )
            == 1
        )
        sequences = list(
            session.scalars(
                select(AgentTurnEventModel.sequence)
                .where(AgentTurnEventModel.turn_id == turn["id"])
                .order_by(AgentTurnEventModel.sequence)
            )
        )
        assert sequences == list(range(1, len(sequences) + 1))
