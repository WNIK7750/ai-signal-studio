from __future__ import annotations

import json

from fastapi.testclient import TestClient

from ai_signal_api.modules.agent_assets.agent_packs import AgentPackService


COLLECT_PROMPT = (
    "你好，请你帮我收集最近24小时的热点AI内容，并选出其中影响力最大的三个，给我分析总结"
)
EXISTING_PROMPT = (
    "那么请你就目前收集的三天内的热点AI内容，并选出其中影响力最大的三个，给我分析总结"
)


def _create(
    client: TestClient,
    conversation_id: str,
    prompt: str,
    client_message_id: str,
) -> dict:
    model_id = client.get("/api/models").json()[0]["id"]
    response = client.post(
        f"/api/agent-conversations/{conversation_id}/turns",
        json={
            "message": prompt,
            "client_message_id": client_message_id,
            "model_id": model_id,
            "artifact_ids": [],
        },
    )
    assert response.status_code == 202
    turn = client.get(
        f"/api/agent-turns/{response.json()['id']}"
    ).json()
    assert turn["status"] in {"complete", "partial"}, turn
    assert turn["workflow_version"] == "0.8.0"
    assert turn["requested_model_id"] == model_id
    assert turn["effective_model_id"] == model_id
    return turn


def _assert_complex_result(
    turn: dict,
    *,
    hours: int,
    mode: str,
    collect: bool,
) -> None:
    result = turn["result"]
    goal = result["goal"]
    assert goal["operation_mode"] == mode
    assert goal["time_window"]["lookback_hours"] == hours
    assert goal["max_items"] == 3
    assert goal["ranking_criterion"] == "impact"
    assert goal["requires_collection"] is collect
    assert goal["requires_synthesis"] is True

    capabilities = [
        step["capability_id"] for step in result["plan"]["steps"]
    ]
    expected = [
        "intelligence.search",
        "research.recommend",
        "research.trend_brief",
    ]
    if collect:
        expected.insert(0, "collection.run.start")
        expected.insert(2, "web.search.collect")
    assert capabilities == expected

    block_types = [block["type"] for block in result["result_blocks"]]
    required = {
        "result_summary",
        "plan_summary",
        "recommendation_list",
        "trend_summary",
        "evidence_sources",
        "navigation_action",
    }
    assert required.issubset(block_types)
    assert block_types.count("result_summary") == 1
    assert block_types.count("evidence_sources") == 1
    assert ("collection_summary" in block_types) is collect

    recommendations = next(
        block
        for block in result["result_blocks"]
        if block["type"] == "recommendation_list"
    )["data"]["items"]
    assert 1 <= len(recommendations) <= 3
    for item in recommendations:
        assert item["information_id"].startswith("info_")
        assert item["source_id"]
        assert item["source_url"].startswith("https://")
        assert item["color"] in {"important", "watch", "normal"}
        assert item["ranking_basis"]
        assert item["app_path"].startswith("/timeline?")

    trend = next(
        block
        for block in result["result_blocks"]
        if block["type"] == "trend_summary"
    )["data"]
    selected_ids = {item["information_id"] for item in recommendations}
    assert trend["overview"]
    assert trend["key_findings"]
    assert all(
        set(finding["information_ids"]).issubset(selected_ids)
        for finding in trend["key_findings"]
    )


def test_agent_falls_back_to_builtin_context_when_agent_pack_is_unavailable(
    client: TestClient,
    tmp_path,
) -> None:
    with client.app.state.session_factory() as session:
        active = AgentPackService(
            session,
            client.app.state.settings.agent_pack_root,
        ).get_active("ai-editor")
        active.storage_uri = str(tmp_path / "unavailable-pack")
        session.commit()

    conversation = client.post("/api/agent-conversations", json={}).json()
    turn = _create(
        client,
        conversation["id"],
        COLLECT_PROMPT,
        "agent-pack-fallback",
    )

    assert turn["manifest"]["agent_pack_version"] == "built-in-defaults"
    events = client.get(f"/api/agent-turns/{turn['id']}/events")
    assert "context.customization.fallback" in events.text
    assert "AGENT_PACK_UNAVAILABLE" in events.text


def test_original_prompts_run_through_one_turn_runtime_and_share_context(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()

    first = _create(
        client,
        conversation["id"],
        COLLECT_PROMPT,
        "complex-original-24h",
    )
    _assert_complex_result(
        first,
        hours=24,
        mode="collect_then_analyze",
        collect=True,
    )
    second = _create(
        client,
        conversation["id"],
        EXISTING_PROMPT,
        "complex-original-72h",
    )
    _assert_complex_result(
        second,
        hours=72,
        mode="analyze_existing",
        collect=False,
    )
    assert second["manifest"]["artifact_ids"] == []
    second_plan_block = next(
        block
        for block in second["result"]["result_blocks"]
        if block["type"] == "plan_summary"
    )
    prior_refs = second_plan_block["data"]["context_refs"]
    assert prior_refs[0]["turn_id"] == first["id"]
    assert prior_refs[0]["business_run_ids"] == first["result"][
        "business_run_ids"
    ]

    invocations = client.get("/api/capability-invocations").json()
    first_calls = [
        item["capability_id"]
        for item in reversed(invocations)
        if item["request_id"] == first["request_id"]
    ]
    second_calls = [
        item["capability_id"]
        for item in reversed(invocations)
        if item["request_id"] == second["request_id"]
    ]
    assert first_calls == [
        "collection.run.start",
        "intelligence.search",
        "web.search.collect",
        "research.recommend",
        "research.trend_brief",
    ]
    assert second_calls == [
        "intelligence.search",
        "research.recommend",
        "research.trend_brief",
    ]


def test_result_block_sse_contains_complete_validated_blocks(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    turn = _create(
        client,
        conversation["id"],
        COLLECT_PROMPT,
        "complex-sse-blocks",
    )
    response = client.get(f"/api/agent-turns/{turn['id']}/events")
    payloads = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    blocks = [
        payload
        for payload in payloads
        if {"block_id", "type", "title", "data"}.issubset(payload)
    ]
    assert blocks
    assert {block["type"] for block in blocks}.issuperset(
        {"plan_summary", "recommendation_list", "trend_summary"}
    )


def test_contextual_follow_up_uses_model_reasoning_without_forced_tools(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    turn = _create(
        client,
        conversation["id"],
        "请你挑选出刚才收集内容中，影响力最大的三个并进行分析总结",
        "contextual-model-reasoning",
    )

    assert turn["status"] == "complete"
    step = turn["result"]["plan"]["steps"][0]
    assert step["kind"] == "model_reasoning"
    assert step["capability_id"] is None
    response = next(
        block
        for block in turn["result"]["result_blocks"]
        if block["type"] == "model_response"
    )
    assert response["data"]["basis"] == "conversation_context"
    assert response["data"]["effective_model_id"]
    invocations = client.get("/api/capability-invocations").json()
    assert all(
        item["request_id"] != turn["request_id"]
        for item in invocations
    )


def test_zero_new_collection_items_still_queries_ranks_and_synthesizes(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    _create(
        client,
        conversation["id"],
        COLLECT_PROMPT,
        "complex-seed-first",
    )
    duplicate = _create(
        client,
        conversation["id"],
        COLLECT_PROMPT,
        "complex-all-duplicates",
    )
    collection = next(
        block
        for block in duplicate["result"]["result_blocks"]
        if block["type"] == "collection_summary"
    )
    assert collection["data"]["items_added"] == 0
    _assert_complex_result(
        duplicate,
        hours=24,
        mode="collect_then_analyze",
        collect=True,
    )
    calls = [
        item["capability_id"]
        for item in reversed(
            client.get("/api/capability-invocations").json()
        )
        if item["request_id"] == duplicate["request_id"]
    ]
    assert calls == [
        "collection.run.start",
        "intelligence.search",
        "web.search.collect",
        "research.recommend",
        "research.trend_brief",
    ]


def test_legacy_agent_runs_adapter_delegates_to_turn_runtime_idempotently(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    payload = {
        "message": COLLECT_PROMPT,
        "conversation_id": conversation["id"],
        "client_message_id": "legacy-complex-idempotent",
    }
    first = client.post("/api/agent-runs", json=payload)
    assert first.status_code == 200
    body = first.json()
    assert body["result"]["goal"]["operation_mode"] == "collect_then_analyze"
    assert [
        call["capability_id"] for call in body["capability_calls"]
    ] == [
        "collection.run.start",
        "intelligence.search",
        "web.search.collect",
        "research.recommend",
        "research.trend_brief",
    ]
    invocation_count = len(client.get("/api/capability-invocations").json())

    second = client.post("/api/agent-runs", json=payload)
    assert second.status_code == 200
    assert second.json()["assistant_message_id"] == body["assistant_message_id"]
    assert (
        len(client.get("/api/capability-invocations").json())
        == invocation_count
    )
