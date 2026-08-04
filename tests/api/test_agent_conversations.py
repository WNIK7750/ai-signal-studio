from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.main import create_app


def test_agent_turn_is_persisted_and_can_be_read_after_refresh(
    client: TestClient,
) -> None:
    conversation = client.get("/api/agent-conversations/current")
    assert conversation.status_code == 200
    conversation_id = conversation.json()["id"]

    response = client.post(
        "/api/agent-runs",
        json={
            "conversation_id": conversation_id,
            "client_message_id": "message-refresh-1",
            "message": "请立即采集最新 AI 信息",
            "model_id": "missing-model-must-not-block-collection",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"] == conversation_id
    assert body["capability_calls"][0]["capability_id"] == (
        "collection.run.start"
    )

    refreshed = client.get("/api/agent-conversations/current").json()
    assert refreshed["id"] == conversation_id
    assert [message["role"] for message in refreshed["messages"]] == [
        "user",
        "assistant",
    ]
    assert refreshed["messages"][0]["content"] == (
        "请立即采集最新 AI 信息"
    )
    assert refreshed["messages"][0]["image_count"] == 0
    assert refreshed["messages"][1]["capability_calls"][0][
        "capability_id"
    ] == "collection.run.start"


def test_retrying_the_same_client_message_does_not_collect_twice(
    client: TestClient,
) -> None:
    payload = {
        "client_message_id": "message-idempotent-1",
        "message": "收集最新 AI 信息",
    }

    first = client.post("/api/agent-runs", json=payload)
    second = client.post("/api/agent-runs", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["assistant_message_id"] == first.json()[
        "assistant_message_id"
    ]
    assert len(client.get("/api/collection-runs").json()) == 1
    history = client.get("/api/agent-conversations/current").json()
    assert len(history["messages"]) == 2


def test_collection_result_explains_zero_new_items(
    client: TestClient,
) -> None:
    client.post("/api/collection-runs", json={})

    response = client.post(
        "/api/agent-runs",
        json={
            "client_message_id": "message-no-new-items",
            "message": "更新 AI 信息",
        },
    )

    assert response.status_code == 200
    assert response.json()["result"]["status"] == "completed"
    assert "没有新增" in response.json()["message"]


def test_no_enabled_sources_is_a_saved_and_observable_failure(
    client: TestClient,
) -> None:
    for source in client.get("/api/sources").json():
        client.patch(
            f"/api/sources/{source['id']}",
            json={"enabled": False},
        )

    response = client.post(
        "/api/agent-runs",
        json={
            "client_message_id": "message-no-sources",
            "message": "采集最新 AI 信息",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "failed"
    assert "未完成" in body["message"]
    assert body["capability_calls"][0]["status"] == "failed"

    invocations = client.get("/api/capability-invocations").json()
    assert invocations[0]["status"] == "failed"
    assert invocations[0]["error_code"] == "NO_ENABLED_SOURCES"

    history = client.get("/api/agent-conversations/current").json()
    assert history["messages"][-1]["error_code"] == "NO_ENABLED_SOURCES"


def test_normal_workspace_seeds_live_sources_instead_of_demo_data(
    tmp_path,
) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=(
                f"sqlite:///{(tmp_path / 'live-sources.db').as_posix()}"
            ),
            source_seed_mode="live",
            model_config_path=tmp_path / "models.local.json",
            model_secrets_path=tmp_path / "model-secrets.local.json",
        ),
        seed_demo_sources=None,
    )

    with TestClient(app) as live_client:
        sources = live_client.get("/api/sources").json()

    assert sources
    assert all(source["kind"] != "demo" for source in sources)
    assert any(
        source["kind"] == "rss"
        and source["config"].get("url") == "https://openai.com/news/rss.xml"
        for source in sources
    )
    assert any(
        source["kind"] == "github_releases"
        and source["config"].get("repository") == "langchain-ai/langgraph"
        for source in sources
    )


def test_source_configuration_is_rejected_before_a_broken_run(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/sources",
        json={
            "name": "配置不完整的 RSS",
            "kind": "rss",
            "config": {},
            "enabled": True,
        },
    )

    assert response.status_code == 422
    assert "SOURCE_CONFIG_URL_REQUIRED" in response.text
