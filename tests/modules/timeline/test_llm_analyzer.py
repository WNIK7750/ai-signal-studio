import json
from datetime import datetime, timezone

import httpx

from ai_signal_api.config import Settings
from ai_signal_api.integrations.llm.config import resolve_llm_runtime
from ai_signal_api.modules.collection.collectors import CollectedItem
from ai_signal_api.modules.intelligence.llm_analyzer import (
    OpenAICompatibleAnalyzer,
    build_analyzer,
)
from ai_signal_api.modules.intelligence.service import HeuristicAnalyzer


def test_heuristic_analyzer_remains_the_default() -> None:
    analyzer = build_analyzer(Settings(_env_file=None))

    assert isinstance(analyzer, HeuristicAnalyzer)


def test_openai_compatible_analyzer_reads_runtime_config_and_validates_output(
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "summary": "经过验证的简短摘要。",
                                    "topics": ["Agent", "模型与工具"],
                                    "priority": "important",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_api_key="sk-test-secret",
        llm_base_url="https://provider.example/v1",
        llm_model="configured-model",
        llm_max_output_tokens=800,
    )
    runtime = resolve_llm_runtime(settings)
    assert runtime is not None
    client = httpx.Client(transport=httpx.MockTransport(handler))
    analyzer = OpenAICompatibleAnalyzer(runtime, client=client)

    result = analyzer.analyze(
        CollectedItem(
            external_id="provider-test",
            title="OpenAI 发布新的 Agent 能力",
            url="https://example.test/item",
            description="这是待分析的来源摘要。",
            published_at=datetime.now(timezone.utc),
        )
    )

    assert result.summary == "经过验证的简短摘要。"
    assert result.topics == ["Agent", "模型与工具"]
    assert result.priority == "important"
    assert captured["authorization"] == "Bearer sk-test-secret"
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["body"] == {
        "model": "configured-model",
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 AI 信息分析器。只返回 JSON，字段为 summary、"
                    "topics、priority。priority 只能是 important、watch、normal。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "标题：OpenAI 发布新的 Agent 能力\n"
                    "原始摘要：这是待分析的来源摘要。"
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 800,
    }
