from fastapi.testclient import TestClient


def _task_payload(source_ids: list[str], **quantity: int) -> dict:
    return {
        "name": "Agent 更新监测",
        "goal": "跟踪 Agent 与 LangGraph 的重要更新",
        "status": "enabled",
        "config": {
            "sources": {
                "mode": "selected",
                "include_ids": source_ids,
            },
            "matching": {
                "topics": [],
                "include_any": ["LangGraph"],
                "include_all": [],
                "exclude": [],
                "search_scope": "title_and_content",
                "languages": ["zh", "en"],
            },
            "time_window": {
                "mode": "rolling",
                "lookback_hours": 24,
                "overlap_hours": 2,
                "timezone": "Asia/Shanghai",
            },
            "quantity": {
                "min_items": quantity.get("min_items", 1),
                "target_items": quantity.get("target_items", 1),
                "max_items": quantity.get("max_items", 2),
            },
            "importance": {
                "accepted_levels": ["important", "watch", "normal"],
            },
            "quality_requirements": {
                "require_source_link": True,
                "prefer_primary_source": True,
                "allow_unknown_publish_time": False,
                "require_extractable_content": True,
            },
            "deduplication": {
                "mode": "balanced",
                "window_days": 31,
                "across_runs": True,
                "preserve_related_sources": True,
            },
            "schedule": {
                "mode": "manual",
                "time_of_day": "09:00",
                "weekdays": [],
                "interval_hours": None,
            },
            "delivery": {
                "destination": "task_view",
                "notify_when": "important_or_problem",
                "summary_max_chars": 400,
            },
        },
    }


def test_task_preview_and_run_use_the_same_structured_rules(
    client: TestClient,
) -> None:
    source_ids = [source["id"] for source in client.get("/api/sources").json()]
    create = client.post(
        "/api/tasks",
        json=_task_payload(source_ids),
    )

    assert create.status_code == 201
    task = create.json()
    assert task["active_version_id"]
    assert task["version_number"] == 1

    preview = client.post(f"/api/tasks/{task['id']}/preview", json={})
    assert preview.status_code == 200
    preview_body = preview.json()
    assert preview_body["funnel_counts"]["fetched"] == 3
    assert preview_body["funnel_counts"]["selected"] == 1
    assert len(preview_body["samples"]) == 1
    assert client.get("/api/timeline").json()["total"] == 0

    run = client.post(f"/api/tasks/{task['id']}/runs", json={})
    assert run.status_code == 201
    run_body = run.json()
    assert run_body["task_id"] == task["id"]
    assert run_body["execution_status"] == "completed"
    assert run_body["coverage_status"] == "met"
    assert run_body["funnel_counts"] == preview_body["funnel_counts"]

    timeline = client.get(
        "/api/timeline",
        params={"task_id": task["id"]},
    ).json()
    assert timeline["total"] == 1
    assert "LangGraph" in timeline["items"][0]["title"]
    assert timeline["items"][0]["task_ids"] == [task["id"]]


def test_quantity_shortfall_is_separate_from_execution_status(
    client: TestClient,
) -> None:
    source_ids = [source["id"] for source in client.get("/api/sources").json()]
    payload = _task_payload(
        source_ids,
        min_items=2,
        target_items=2,
        max_items=2,
    )
    task = client.post("/api/tasks", json=payload).json()

    run = client.post(f"/api/tasks/{task['id']}/runs", json={}).json()

    assert run["execution_status"] == "completed"
    assert run["coverage_status"] == "insufficient"
    assert "TASK_MIN_ITEMS_NOT_MET" in run["warning_codes"]
    assert run["funnel_counts"]["selected"] == 1


def test_task_run_can_retry_original_version(client: TestClient) -> None:
    source_ids = [source["id"] for source in client.get("/api/sources").json()]
    task = client.post(
        "/api/tasks",
        json=_task_payload(source_ids),
    ).json()
    original = client.post(
        f"/api/tasks/{task['id']}/runs",
        json={"trigger_type": "manual"},
    ).json()

    retry = client.post(
        f"/api/task-runs/{original['id']}/retry",
        json={"mode": "original_version"},
    )

    assert retry.status_code == 201
    assert retry.json()["parent_run_id"] == original["id"]
    assert retry.json()["task_version_id"] == original["task_version_id"]
    assert retry.json()["trigger_type"] == "retry"


def test_invalid_quantity_range_is_rejected(client: TestClient) -> None:
    source_ids = [source["id"] for source in client.get("/api/sources").json()]
    payload = _task_payload(
        source_ids,
        min_items=10,
        target_items=5,
        max_items=3,
    )

    response = client.post("/api/tasks", json=payload)

    assert response.status_code == 422
