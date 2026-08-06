import sqlite3

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


def test_agent_task_draft_is_structured_and_survives_refresh(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/agent-runs",
        json={
            "client_message_id": "message-task-draft-1",
            "message": (
                "创建任务：每天上午 9 点收集 OpenAI 和 Agent 信息，"
                "至少 8 条、最多 24 条，摘要最多 600 字"
            ),
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == "pending_confirmation"
    assert body["task_draft"]["config"]["sources"]["mode"] == "all_enabled"
    assert body["task_draft"]["config"]["quantity"] == {
        "min_items": 8,
        "target_items": 10,
        "max_items": 24,
    }
    assert body["task_draft"]["config"]["schedule"]["time_of_day"] == "09:00"
    assert body["task_draft"]["config"]["delivery"][
        "summary_max_chars"
    ] == 600

    refreshed = client.get("/api/agent-conversations/current").json()
    saved = refreshed["messages"][-1]["task_draft"]
    assert saved == body["task_draft"]


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


def test_demo_source_can_be_tested_without_creating_a_collection_run(
    client: TestClient,
) -> None:
    source = next(
        source
        for source in client.get("/api/sources").json()
        if source["kind"] == "demo"
    )

    response = client.post(f"/api/sources/{source['id']}/test")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["items_count"] == 1
    assert client.get("/api/collection-runs").json() == []


def test_agent_conversations_are_isolated_and_manual_titles_are_preserved(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/agent-conversations",
        json={"title": "项目 Alpha"},
    )
    second = client.post("/api/agent-conversations", json={})

    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    for conversation_id, message in (
        (first_id, "查询 OpenAI"),
        (second_id, "查询 LangGraph"),
    ):
        response = client.post(
            "/api/agent-runs",
            json={
                "conversation_id": conversation_id,
                "client_message_id": "shared-browser-message-id",
                "message": message,
            },
        )
        assert response.status_code == 200

    first_detail = client.get(
        f"/api/agent-conversations/{first_id}"
    ).json()
    second_detail = client.get(
        f"/api/agent-conversations/{second_id}"
    ).json()
    assert first_detail["title"] == "项目 Alpha"
    assert first_detail["title_source"] == "manual"
    assert [item["content"] for item in first_detail["messages"]][0] == (
        "查询 OpenAI"
    )
    assert [item["content"] for item in second_detail["messages"]][0] == (
        "查询 LangGraph"
    )


def test_agent_conversation_pin_sort_archive_delete_and_restore(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/agent-conversations",
        json={"title": "普通会话"},
    ).json()
    pinned = client.post(
        "/api/agent-conversations",
        json={"title": "置顶会话"},
    ).json()

    response = client.patch(
        f"/api/agent-conversations/{pinned['id']}",
        json={"pinned": True},
    )
    assert response.status_code == 200
    active = client.get("/api/agent-conversations").json()
    assert active[0]["id"] == pinned["id"]

    for _ in range(2):
        archived = client.post(
            f"/api/agent-conversations/{first['id']}/archive"
        )
        assert archived.status_code == 200
    assert first["id"] not in {
        item["id"] for item in client.get("/api/agent-conversations").json()
    }
    assert first["id"] in {
        item["id"]
        for item in client.get(
            "/api/agent-conversations",
            params={"scope": "archived"},
        ).json()
    }

    restored = client.post(
        f"/api/agent-conversations/{first['id']}/restore"
    )
    assert restored.status_code == 200
    deleted = client.delete(
        f"/api/agent-conversations/{first['id']}"
    )
    assert deleted.status_code == 200
    assert first["id"] in {
        item["id"]
        for item in client.get(
            "/api/agent-conversations",
            params={"scope": "deleted"},
        ).json()
    }
    restored_again = client.post(
        f"/api/agent-conversations/{first['id']}/restore"
    )
    assert restored_again.status_code == 200
    assert restored_again.json()["deleted_at"] is None


def test_agent_conversation_first_message_generates_a_stable_title(
    client: TestClient,
) -> None:
    conversation = client.post("/api/agent-conversations", json={}).json()
    conversation_id = conversation["id"]

    response = client.post(
        "/api/agent-runs",
        json={
            "conversation_id": conversation_id,
            "client_message_id": "auto-title-first-message",
            "message": "帮我查询最近的 OpenAI 产品更新和发布信息",
        },
    )
    assert response.status_code == 200

    detail = client.get(
        f"/api/agent-conversations/{conversation_id}"
    ).json()
    assert detail["title"].startswith("帮我查询最近的 OpenAI")
    assert detail["title_source"] == "auto"

    renamed = client.patch(
        f"/api/agent-conversations/{conversation_id}",
        json={"title": "手动标题"},
    )
    assert renamed.status_code == 200
    client.post(
        "/api/agent-runs",
        json={
            "conversation_id": conversation_id,
            "client_message_id": "auto-title-second-message",
            "message": "再查询 LangGraph",
        },
    )
    assert client.get(
        f"/api/agent-conversations/{conversation_id}"
    ).json()["title"] == "手动标题"


def test_existing_agent_conversation_is_upgraded_without_losing_messages(
    tmp_path,
) -> None:
    database_path = tmp_path / "legacy-agent.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE agent_conversations (
                id VARCHAR(64) PRIMARY KEY,
                title VARCHAR(160) NOT NULL,
                status VARCHAR(24) NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE agent_messages (
                id VARCHAR(64) PRIMARY KEY,
                conversation_id VARCHAR(64) NOT NULL,
                role VARCHAR(24) NOT NULL,
                content TEXT NOT NULL,
                client_message_id VARCHAR(100),
                request_id VARCHAR(80) NOT NULL,
                capability_calls JSON NOT NULL,
                result_data JSON NOT NULL,
                schedule_draft JSON,
                requested_model_id VARCHAR(120),
                effective_model_id VARCHAR(120),
                model_switched BOOLEAN NOT NULL DEFAULT 0,
                error_code VARCHAR(80),
                image_count INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                UNIQUE (conversation_id, client_message_id),
                FOREIGN KEY(conversation_id)
                    REFERENCES agent_conversations (id)
            );
            INSERT INTO agent_conversations VALUES (
                'conversation_legacy',
                '旧会话',
                'active',
                '2026-08-01 09:00:00',
                '2026-08-01 09:00:00'
            );
            INSERT INTO agent_messages VALUES (
                'message_legacy',
                'conversation_legacy',
                'user',
                '保留这条历史消息',
                'legacy-client-message',
                'legacy-request',
                '[]',
                '{}',
                NULL,
                NULL,
                NULL,
                0,
                NULL,
                0,
                '2026-08-01 09:01:00'
            );
            """
        )

    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=f"sqlite:///{database_path.as_posix()}",
            source_seed_mode="none",
            model_config_path=tmp_path / "models.local.json",
            model_secrets_path=tmp_path / "model-secrets.local.json",
        ),
        seed_demo_sources=False,
    )
    with TestClient(app) as legacy_client:
        detail = legacy_client.get(
            "/api/agent-conversations/conversation_legacy"
        )

    assert detail.status_code == 200
    assert detail.json()["last_message_at"].startswith("2026-08-01T09:01:00")
    assert detail.json()["messages"][0]["content"] == "保留这条历史消息"
