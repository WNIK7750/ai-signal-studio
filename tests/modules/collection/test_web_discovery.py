from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx
import pytest
from ai_signal_api.integrations.search.brave import SearchHit
from ai_signal_api.integrations.search.model import (
    FallbackWebSearchProvider,
    ModelWebSearchProvider,
)
from ai_signal_api.modules.models.service import ResolvedModel
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.modules.collection.web_discovery import (
    CrawledPage,
    WebDiscoveryService,
    WebSearchCollectInput,
)


class FakeSearchProvider:
    provider_id = "fake"

    def __init__(self) -> None:
        self.calls = 0

    def search(self, query, *, count, freshness):
        del query, count, freshness
        self.calls += 1
        return [
            SearchHit(
                title="Agent 检索更新",
                url="https://example.com/agent-search",
                description="一个用于 Agent 的统一检索更新。",
                published_at=datetime.now(timezone.utc),
            )
        ]


class FakeCrawler:
    def __init__(self) -> None:
        self.calls = 0

    def crawl(self, hit):
        self.calls += 1
        return CrawledPage(
            url=hit.url,
            title=hit.title,
            excerpt=hit.description,
            content_text=(
                "统一检索先融合本地候选，再让模型进行分级与标签处理。"
            ),
            published_at=hit.published_at,
        )


def test_web_discovery_caches_search_and_pages_before_ingestion(client) -> None:
    session = client.app.state.session_factory()
    provider = FakeSearchProvider()
    crawler = FakeCrawler()
    service = WebDiscoveryService(
        session,
        CollectionService(session),
        provider,
        crawler=crawler,
    )
    try:
        first = service.collect(
            WebSearchCollectInput(
                query="AI Agent 最新动态",
                local_result_count=0,
                minimum_results=3,
            ),
            idempotency_key="web-discovery-1",
        )
        second = service.collect(
            WebSearchCollectInput(
                query="AI Agent 最新动态",
                local_result_count=0,
                minimum_results=3,
            ),
            idempotency_key="web-discovery-2",
        )

        assert first.status == "completed"
        assert first.added_count == 1
        assert first.information_ids
        assert second.cache_hit is True
        assert second.added_count == 0
        assert provider.calls == 1
        assert crawler.calls == 1
    finally:
        session.close()


def test_web_discovery_skips_network_when_local_search_is_sufficient(
    client,
) -> None:
    session = client.app.state.session_factory()
    provider = FakeSearchProvider()
    service = WebDiscoveryService(
        session,
        CollectionService(session),
        provider,
        crawler=FakeCrawler(),
    )
    try:
        result = service.collect(
            WebSearchCollectInput(
                query="AI",
                local_result_count=3,
                minimum_results=3,
            ),
            idempotency_key="web-discovery-skip",
        )
        assert result.skipped is True
        assert provider.calls == 0
        assert "无需联网" in result.summary
    finally:
        session.close()


def test_web_discovery_explains_missing_provider(client) -> None:
    session = client.app.state.session_factory()
    service = WebDiscoveryService(
        session,
        CollectionService(session),
        None,
        crawler=FakeCrawler(),
    )
    try:
        result = service.collect(
            WebSearchCollectInput(query="AI"),
            idempotency_key="web-discovery-no-provider",
        )
        assert result.status == "partial"
        assert result.errors[0]["error_code"] == (
            "SEARCH_PROVIDER_NOT_CONFIGURED"
        )
        assert "尚未配置" in result.summary
    finally:
        session.close()


def test_model_web_search_uses_openai_compatible_responses_citations() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "已检索到两个相关来源。",
                                "annotations": [
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/a",
                                        "title": "来源 A",
                                    },
                                    {
                                        "type": "url_citation",
                                        "url": "https://example.com/b",
                                        "title": "来源 B",
                                    },
                                ],
                            }
                        ],
                    }
                ]
            },
        )

    model = ResolvedModel(
        id="model_search",
        name="搜索模型",
        provider="openai_compatible",
        provider_id="provider_search",
        provider_name="示例",
        model_id="qwen3.7-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-test",
        supports_vision=False,
        output_token_limit=None,
        enabled=True,
        is_default=False,
        is_search_model=True,
    )
    provider = ModelWebSearchProvider(
        model,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    hits = provider.search("AI Agent 最新动态", count=2, freshness="pd")

    assert captured["url"].endswith("/compatible-mode/v1/responses")
    assert captured["body"]["tools"] == [{"type": "web_search"}]
    assert [hit.title for hit in hits] == ["来源 A", "来源 B"]
    assert provider.provider_id == "model:model_search"


def test_model_search_rejects_an_uncited_answer() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "只有模型文字，没有可追溯引用。",
                                "annotations": [],
                            }
                        ],
                    }
                ]
            },
        )

    model = ResolvedModel(
        id="model_search",
        name="搜索模型",
        provider="openai_compatible",
        provider_id="provider_search",
        provider_name="示例",
        model_id="qwen3.7-plus",
        base_url="https://example.com/v1",
        api_key="sk-test",
        supports_vision=False,
        output_token_limit=None,
        enabled=True,
        is_default=False,
        is_search_model=True,
    )
    provider = ModelWebSearchProvider(
        model,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ValueError, match="SEARCH_MODEL_NO_CITATIONS"):
        provider.search("AI Agent", count=3, freshness="pd")


def test_search_provider_falls_back_after_a_provider_error() -> None:
    class FailedProvider:
        provider_id = "failed"

        def search(self, *_args, **_kwargs):
            raise ValueError("SEARCH_MODEL_UNAVAILABLE")

    class WorkingProvider:
        provider_id = "working"

        def search(self, *_args, **_kwargs):
            return [
                SearchHit(
                    title="后备来源",
                    url="https://example.com/fallback",
                    description="已通过后备提供商返回。",
                    published_at=None,
                )
            ]

    provider = FallbackWebSearchProvider(
        [FailedProvider(), WorkingProvider()]
    )

    hits = provider.search("AI Agent", count=3, freshness="pd")

    assert hits[0].title == "后备来源"
    assert provider.provider_id == "fallback:failed,working"
