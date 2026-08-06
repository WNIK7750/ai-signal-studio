from __future__ import annotations

from datetime import datetime, timezone

from ai_signal_api.integrations.search.brave import SearchHit
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
