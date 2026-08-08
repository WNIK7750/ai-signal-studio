import json

import httpx
from fastapi.testclient import TestClient

from ai_signal_api.integrations.llm.chat import OpenAICompatibleModelChat


ONE_PIXEL_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
    "QVQ42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def create_vision_model(client: TestClient) -> dict:
    response = client.post(
        "/api/models",
        json={
            "name": "视觉模型",
            "model_id": "vision-model-v1",
            "provider_name": "示例提供商",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-vision-secret",
            "supports_vision": True,
            "output_token_limit": 16000,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_models_can_be_created_and_switched_as_workspace_default(
    client: TestClient,
) -> None:
    initial_models = client.get("/api/models").json()
    assert len(initial_models) == 1
    assert initial_models[0]["is_default"] is True
    assert initial_models[0]["supports_vision"] is False

    vision_model = create_vision_model(client)
    response = client.post(f"/api/models/{vision_model['id']}/activate")

    assert response.status_code == 200
    assert response.json()["is_default"] is True
    models = client.get("/api/models").json()
    assert sum(model["is_default"] for model in models) == 1


def test_provider_key_is_file_managed_and_never_returned(
    client: TestClient,
) -> None:
    vision_model = create_vision_model(client)
    settings = client.app.state.settings
    model_file = settings.model_config_path.read_text(encoding="utf-8")
    secret_file = settings.model_secrets_path.read_text(encoding="utf-8")

    response_text = client.get("/api/models").text
    providers = client.get("/api/providers").json()

    assert "sk-vision-secret" not in response_text
    assert "sk-vision-secret" not in model_file
    assert "sk-vision-secret" in secret_file
    assert "api_key" not in vision_model
    assert vision_model["has_api_key"] is True
    assert vision_model["provider_name"] == "示例提供商"
    assert providers == [
        {
            "id": vision_model["provider_id"],
            "name": "示例提供商",
            "base_url": "https://api.example.com/v1",
            "protocol": "openai_compatible",
            "has_api_key": True,
            "model_names": ["视觉模型"],
        }
    ]


def test_external_model_cannot_be_saved_without_api_key(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/models",
        json={
            "name": "未配置模型",
            "model_id": "missing-key-model",
            "provider_name": "示例提供商",
            "base_url": "https://api.example.com/v1",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "SECRET-003（请填写 API Key）"
    assert len(client.get("/api/models").json()) == 1


def test_saved_model_can_test_its_real_provider_request(
    client: TestClient,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    model = create_vision_model(client)
    client.app.state.model_chat = OpenAICompatibleModelChat(
        client.app.state.settings,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client.post(f"/api/models/{model['id']}/test")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "message": "MODEL-000（连接成功）",
    }
    assert captured["authorization"] == "Bearer sk-vision-secret"
    assert captured["url"] == "https://api.example.com/v1/chat/completions"
    assert captured["body"]["model"] == "vision-model-v1"
    tested = next(
        item
        for item in client.get("/api/models").json()
        if item["id"] == model["id"]
    )
    assert tested["connection_status"] == "healthy"
    assert tested["connection_checked_at"]


def test_connection_is_pending_only_for_new_or_edited_model(
    client: TestClient,
) -> None:
    model = create_vision_model(client)
    assert model["connection_status"] == "pending"
    assert model["connection_checked_at"] is None

    selected = client.app.state.model_configuration.select_for_request(
        model["id"]
    )
    assert selected.effective_model.id == model["id"]
    unchanged = next(
        item
        for item in client.get("/api/models").json()
        if item["id"] == model["id"]
    )
    assert unchanged["connection_status"] == "pending"

    response = client.patch(
        f"/api/models/{model['id']}",
        json={"name": "视觉模型（已修改）"},
    )
    assert response.status_code == 200
    assert response.json()["connection_status"] == "pending"
    assert response.json()["connection_checked_at"] is None


def test_existing_provider_can_reuse_its_key_for_another_model(
    client: TestClient,
) -> None:
    first = create_vision_model(client)
    response = client.post(
        "/api/models",
        json={
            "name": "文本模型",
            "model_id": "text-model-v1",
            "provider_id": first["provider_id"],
            "base_url": "https://ignored.example/v1",
            "supports_vision": False,
        },
    )

    assert response.status_code == 201
    second = response.json()
    assert second["provider_id"] == first["provider_id"]
    assert second["has_api_key"] is True
    assert second["base_url"] == "https://api.example.com/v1"
    provider = client.get("/api/providers").json()[0]
    assert provider["model_names"] == ["视觉模型", "文本模型"]


def test_external_model_can_be_selected_as_the_only_search_model(
    client: TestClient,
) -> None:
    first = create_vision_model(client)
    second = client.post(
        "/api/models",
        json={
            "name": "联网检索模型",
            "model_id": "search-model-v1",
            "provider_id": first["provider_id"],
        },
    ).json()

    response = client.post(f"/api/models/{second['id']}/activate-search")

    assert response.status_code == 200
    assert response.json()["is_search_model"] is True
    models = client.get("/api/models").json()
    assert sum(model["is_search_model"] for model in models) == 1
    selected = client.app.state.model_configuration.select_for_search()
    assert selected is not None
    assert selected.id == second["id"]


def test_local_rules_model_cannot_be_selected_for_web_search(
    client: TestClient,
) -> None:
    response = client.post("/api/models/model_local/activate-search")

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "MODEL-009（当前模型不支持原生联网搜索）"
    )


def test_different_providers_keep_different_keys(
    client: TestClient,
) -> None:
    first = create_vision_model(client)
    response = client.post(
        "/api/models",
        json={
            "name": "另一个模型",
            "model_id": "another-model-v1",
            "provider_name": "另一个提供商",
            "base_url": "https://another.example/v1",
            "api_key": "sk-another-secret",
        },
    )

    assert response.status_code == 201
    second = response.json()
    assert second["provider_id"] != first["provider_id"]
    secret_file = (
        client.app.state.settings.model_secrets_path.read_text(
            encoding="utf-8"
        )
    )
    assert "sk-vision-secret" in secret_file
    assert "sk-another-secret" in secret_file
    assert "sk-another-secret" not in client.get("/api/models").text


def test_model_can_be_edited_without_returning_its_replaced_key(
    client: TestClient,
) -> None:
    model = create_vision_model(client)

    response = client.patch(
        f"/api/models/{model['id']}",
        json={
            "name": "视觉模型 Pro",
            "model_id": "vision-model-v2",
            "provider_name": "新提供商名称",
            "base_url": "https://new.example.com/v1",
            "api_key": "sk-replaced-secret",
            "supports_vision": True,
            "output_token_limit": 32000,
            "is_default": True,
        },
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "视觉模型 Pro"
    assert updated["model_id"] == "vision-model-v2"
    assert updated["provider_name"] == "新提供商名称"
    assert updated["base_url"] == "https://new.example.com/v1"
    assert updated["supports_vision"] is True
    assert updated["output_token_limit"] == 32000
    assert updated["is_default"] is True
    assert "api_key" not in updated
    assert "sk-replaced-secret" not in response.text
    assert "sk-replaced-secret" in (
        client.app.state.settings.model_secrets_path.read_text(
            encoding="utf-8"
        )
    )


def test_deleting_default_model_soft_deletes_and_restores_local_default(
    client: TestClient,
) -> None:
    model = create_vision_model(client)
    client.post(f"/api/models/{model['id']}/activate")

    response = client.delete(f"/api/models/{model['id']}")

    assert response.status_code == 204
    models = client.get("/api/models").json()
    assert all(item["id"] != model["id"] for item in models)
    assert models[0]["id"] == "model_local"
    assert models[0]["is_default"] is True

    config = json.loads(
        client.app.state.settings.model_config_path.read_text(
            encoding="utf-8"
        )
    )
    deleted = next(
        item for item in config["models"] if item["id"] == model["id"]
    )
    assert deleted["enabled"] is False
    assert deleted["is_default"] is False

    agent_response = client.post(
        "/api/agent-runs",
        json={"message": "你好", "model_id": model["id"]},
    ).json()
    assert agent_response["message"] == "MODEL-001（未找到指定模型）"


def test_built_in_model_cannot_be_edited_or_deleted(
    client: TestClient,
) -> None:
    patch_response = client.patch(
        "/api/models/model_local",
        json={"name": "修改内置模型"},
    )
    delete_response = client.delete("/api/models/model_local")

    assert patch_response.status_code == 409
    assert patch_response.json()["detail"] == (
        "MODEL-007（内置模型不可修改）"
    )
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == (
        "MODEL-007（内置模型不可修改）"
    )


def test_activating_an_unknown_model_uses_numbered_chinese_error(
    client: TestClient,
) -> None:
    response = client.post("/api/models/model_missing/activate")

    assert response.status_code == 404
    assert response.json()["detail"] == "MODEL-001（未找到指定模型）"


def test_image_request_never_forces_a_model_switch(
    client: TestClient,
) -> None:
    selected_model = client.get("/api/models").json()[0]
    create_vision_model(client)

    response = client.post(
        "/api/agent-runs",
        json={
            "message": "请分析这张图",
            "model_id": selected_model["id"],
            "image_urls": [ONE_PIXEL_PNG],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_model_id"] == selected_model["id"]
    assert body["effective_model_id"] == selected_model["id"]
    assert body["model_switched"] is False
    assert body["result"] == {
        "status": "failed",
        "error_code": "MODEL-002",
    }
    assert body["message"] == "MODEL-002（当前模型不支持图片）"


def test_selected_vision_model_receives_uploaded_image(
    client: TestClient,
) -> None:
    vision_model = create_vision_model(client)

    response = client.post(
        "/api/agent-runs",
        json={
            "message": "请分析这张图",
            "model_id": vision_model["id"],
            "image_urls": [ONE_PIXEL_PNG],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["effective_model_id"] == vision_model["id"]
    assert body["model_switched"] is False
    assert body["message"] == "视觉模型回复：已收到1张图片。"


def test_non_vision_model_writes_image_error_to_agent_output(
    client: TestClient,
) -> None:
    selected_model = client.get("/api/models").json()[0]

    response = client.post(
        "/api/agent-runs",
        json={
            "message": "请分析这张图",
            "model_id": selected_model["id"],
            "image_urls": [ONE_PIXEL_PNG],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["message"] == (
        "MODEL-002（当前模型不支持图片）"
    )
    assert body["effective_model_id"] == selected_model["id"]
    assert body["result"] == {
        "status": "failed",
        "error_code": "MODEL-002",
    }


def test_unknown_dialogue_model_writes_numbered_error_to_agent_output(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/agent-runs",
        json={
            "message": "查询 Agent 信息",
            "model_id": "model_missing",
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "MODEL-001（未找到指定模型）"
