from fastapi.testclient import TestClient


def test_workspace_agent_uses_the_same_collection_capability(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/agent-runs",
        json={"message": "请立即采集最新 AI 情报"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["capability_calls"][0]["capability_id"] == "collection.run.start"
    assert body["capability_calls"][0]["status"] == "completed"

    invocations = client.get("/api/capability-invocations").json()
    collection_calls = [
        item
        for item in invocations
        if item["capability_id"] == "collection.run.start"
    ]
    assert collection_calls
    assert collection_calls[0]["actor_type"] == "internal_agent"


def test_workspace_agent_can_query_the_timeline(client: TestClient) -> None:
    client.post("/api/collection-runs", json={})

    response = client.post(
        "/api/agent-runs",
        json={"message": "查询时间线里 LangGraph 的消息"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["capability_calls"][0]["capability_id"] == (
        "intelligence.timeline.query"
    )
    assert body["result"]["total"] >= 1


def test_common_plan_and_daily_schedule_can_be_created_and_edited(
    client: TestClient,
) -> None:
    plan_response = client.post(
        "/api/plans",
        json={
            "name": "每日 AI 要闻·自定义",
            "prompt": "收集过去 24 小时内的重要 AI 信息",
            "time_range_hours": 24,
            "topics": ["Agent", "模型与工具"],
            "source_ids": [],
        },
    )
    assert plan_response.status_code == 201
    plan = plan_response.json()

    update_response = client.patch(
        f"/api/plans/{plan['id']}",
        json={"topics": ["Agent", "AI Coding"]},
    )
    assert update_response.status_code == 200
    assert update_response.json()["topics"] == ["Agent", "AI Coding"]

    schedule_response = client.post(
        "/api/scheduled-tasks",
        json={
            "name": "每日 AI 要闻·自定义",
            "plan_id": plan["id"],
            "frequency": "daily",
            "time_of_day": "09:00",
            "enabled": True,
        },
    )
    assert schedule_response.status_code == 201
    schedule = schedule_response.json()
    assert schedule["enabled"] is True
    assert schedule["next_run_at"] is not None

    reschedule_response = client.patch(
        f"/api/scheduled-tasks/{schedule['id']}",
        json={"time_of_day": "10:30", "enabled": True},
    )
    assert reschedule_response.status_code == 200
    assert reschedule_response.json()["time_of_day"] == "10:30"
