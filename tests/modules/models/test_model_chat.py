import json

import httpx
import pytest

from ai_signal_api.config import Settings
from ai_signal_api.integrations.llm.chat import (
    ModelChatError,
    OpenAICompatibleModelChat,
)
from ai_signal_api.modules.models.service import ResolvedModel


def test_openai_compatible_chat_uses_selected_model_and_image() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "图片中展示了上升趋势。"}}
                ]
            },
        )

    adapter = OpenAICompatibleModelChat(
        Settings(
            _env_file=None,
            llm_timeout_seconds=12,
            llm_max_output_tokens=640,
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    model = ResolvedModel(
        id="model_vision",
        name="视觉模型",
        provider="openai_compatible",
        provider_id="provider_test",
        provider_name="测试提供商",
        model_id="vision-model-v1",
        base_url="https://provider.example/v1/chat/completions",
        api_key="sk-test-secret",
        supports_vision=True,
        output_token_limit=None,
        enabled=True,
        is_default=True,
    )

    result = adapter.complete(
        model,
        "请分析这张图",
        ["https://example.com/chart.png"],
    )

    assert result == "图片中展示了上升趋势。"
    assert captured["authorization"] == "Bearer sk-test-secret"
    assert captured["url"] == (
        "https://provider.example/v1/chat/completions"
    )
    assert captured["body"] == {
        "model": "vision-model-v1",
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 AI Signal Studio 的工作区助手。"
                    "使用简洁中文直接回答，不虚构未提供的信息。"
                ),
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请分析这张图"},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://example.com/chart.png"
                        },
                    },
                ],
            },
        ],
        "max_tokens": 640,
    }


def test_chat_without_environment_key_uses_numbered_error() -> None:
    adapter = OpenAICompatibleModelChat(Settings(_env_file=None))
    model = ResolvedModel(
        id="model_vision",
        name="视觉模型",
        provider="openai_compatible",
        provider_id="provider_test",
        provider_name="测试提供商",
        model_id="vision-model-v1",
        base_url="https://provider.example/v1",
        api_key=None,
        supports_vision=True,
        output_token_limit=None,
        enabled=True,
        is_default=True,
    )

    with pytest.raises(
        ModelChatError,
        match=r"MODEL-003（模型配置不完整）",
    ):
        adapter.complete(model, "你好", [])


@pytest.mark.parametrize(
    ("status_code", "expected_error"),
    [
        (401, r"SECRET-004（API Key 无效或无权限）"),
        (404, r"PROVIDER-003（接口地址或模型 ID 不可用）"),
        (429, r"PROVIDER-005（模型服务请求受限）"),
    ],
)
def test_chat_maps_provider_status_to_actionable_error(
    status_code: int,
    expected_error: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": "provider detail"})

    adapter = OpenAICompatibleModelChat(
        Settings(_env_file=None),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    model = ResolvedModel(
        id="model_text",
        name="文本模型",
        provider="openai_compatible",
        provider_id="provider_test",
        provider_name="测试提供商",
        model_id="text-model-v1",
        base_url="https://provider.example/v1",
        api_key="sk-test-secret",
        supports_vision=False,
        output_token_limit=None,
        enabled=True,
        is_default=True,
    )

    with pytest.raises(ModelChatError, match=expected_error):
        adapter.complete(model, "你好", [])
