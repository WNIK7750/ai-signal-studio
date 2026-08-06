from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Literal, Protocol
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.integrations.search.brave import (
    SearchHit,
    WebSearchProvider,
)
from ai_signal_api.models import (
    SourceConfigModel,
    WebPageCacheModel,
    WebSearchCacheModel,
)
from ai_signal_api.modules.collection.collectors import (
    CollectedItem,
    SafeHttpClient,
)
from ai_signal_api.modules.collection.service import (
    CollectionService,
    canonicalize_url,
)


class WebSearchCollectInput(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=8, ge=1, le=20)
    freshness: Literal["pd", "pw", "pm", "py"] | None = None
    local_result_count: int = Field(default=0, ge=0, le=10000)
    minimum_results: int = Field(default=3, ge=1, le=20)
    cache_ttl_hours: int = Field(default=12, ge=1, le=168)


class WebSearchCollectResult(BaseModel):
    status: Literal["completed", "partial", "failed"] = "completed"
    summary: str
    provider: str | None = None
    skipped: bool = False
    cache_hit: bool = False
    searched_count: int = 0
    crawled_count: int = 0
    added_count: int = 0
    information_ids: list[str] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class CrawledPage:
    url: str
    title: str
    excerpt: str
    content_text: str
    published_at: datetime | None


class PageCrawler(Protocol):
    def crawl(self, hit: SearchHit) -> CrawledPage: ...


class _ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.description = ""
        self.published_at: datetime | None = None
        self._ignored_depth = 0
        self._in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        tag = tag.lower()
        attributes = {
            key.lower(): (value or "")
            for key, value in attrs
        }
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
            ).lower()
            content = attributes.get("content", "").strip()
            if key in {"description", "og:description"} and content:
                self.description = self.description or content
            if key in {
                "article:published_time",
                "date",
                "datepublished",
            }:
                self.published_at = (
                    self.published_at or self._parse_date(content)
                )

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored_depth = max(self._ignored_depth - 1, 0)
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split()).strip()
        if not value or self._ignored_depth:
            return
        if self._in_title:
            self.title_parts.append(value)
        else:
            self.text_parts.append(value)

    @staticmethod
    def _parse_date(value: str) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class SafePageCrawler:
    USER_AGENT = "AI-Signal-Studio/0.7"

    def __init__(
        self,
        client: SafeHttpClient | None = None,
        *,
        max_content_chars: int = 20_000,
    ) -> None:
        self.client = client or SafeHttpClient(max_bytes=2_000_000)
        self.max_content_chars = max_content_chars

    def crawl(self, hit: SearchHit) -> CrawledPage:
        self._check_robots(hit.url)
        response = self.client.get(
            hit.url,
            headers={"User-Agent": self.USER_AGENT},
            allowed_types=(
                "text/html",
                "application/xhtml+xml",
                "text/plain",
            ),
        )
        parser = _ReadableHtmlParser()
        parser.feed(response.text)
        content = " ".join(parser.text_parts)
        content = re.sub(r"\s+", " ", content).strip()
        title = " ".join(parser.title_parts).strip() or hit.title
        excerpt = parser.description or hit.description or content[:600]
        return CrawledPage(
            url=str(response.url),
            title=title[:500],
            excerpt=excerpt[:1200],
            content_text=content[: self.max_content_chars],
            published_at=parser.published_at or hit.published_at,
        )

    def _check_robots(self, url: str) -> None:
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        try:
            response = self.client.get(
                robots_url,
                headers={"User-Agent": self.USER_AGENT},
                allowed_types=("text/plain",),
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code in {401, 403}:
                raise ValueError("WEB_CRAWL_ROBOTS_DENIED") from error
            return
        except (httpx.HTTPError, ValueError):
            return
        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        if not parser.can_fetch(self.USER_AGENT, url):
            raise ValueError("WEB_CRAWL_ROBOTS_DENIED")


class WebDiscoveryService:
    def __init__(
        self,
        session: Session,
        collection: CollectionService,
        provider: WebSearchProvider | None,
        *,
        crawler: PageCrawler | None = None,
    ) -> None:
        self.session = session
        self.collection = collection
        self.provider = provider
        self.crawler = crawler or SafePageCrawler()

    def collect(
        self,
        filters: WebSearchCollectInput,
        *,
        idempotency_key: str | None,
    ) -> WebSearchCollectResult:
        if filters.local_result_count >= filters.minimum_results:
            return WebSearchCollectResult(
                summary=(
                    f"本地统一检索已有 {filters.local_result_count} 条候选，"
                    "无需联网补充。"
                ),
                skipped=True,
            )
        if self.provider is None:
            return WebSearchCollectResult(
                status="partial",
                summary=(
                    "本地证据不足，但尚未配置联网搜索提供商。"
                    "请在本地环境配置搜索 API 密钥后重试。"
                ),
                errors=[
                    {
                        "error_code": "SEARCH_PROVIDER_NOT_CONFIGURED",
                        "message": "未配置搜索 API 密钥。",
                    }
                ],
            )

        now = datetime.now(timezone.utc)
        query_digest = hashlib.sha256(
            json.dumps(
                {
                    "provider": self.provider.provider_id,
                    "query": filters.query,
                    "freshness": filters.freshness,
                    "limit": filters.limit,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        cached_search = self.session.scalar(
            select(WebSearchCacheModel).where(
                WebSearchCacheModel.query_digest == query_digest
            )
        )
        if (
            cached_search is not None
            and self._aware(cached_search.expires_at) > now
        ):
            hits = [
                SearchHit(title="", url=url, description="")
                for url in cached_search.result_urls
            ]
            cache_hit = True
        else:
            try:
                hits = self.provider.search(
                    filters.query,
                    count=filters.limit,
                    freshness=filters.freshness,
                )
            except Exception as error:
                return WebSearchCollectResult(
                    status="partial",
                    summary="联网搜索失败，未写入不完整结果。",
                    provider=self.provider.provider_id,
                    errors=[
                        {
                            "error_code": self._error_code(error),
                            "message": str(error)[:300],
                        }
                    ],
                )
            cache_hit = False
            if cached_search is None:
                cached_search = WebSearchCacheModel(
                    provider=self.provider.provider_id,
                    query_digest=query_digest,
                    query=filters.query,
                    freshness=filters.freshness,
                    result_urls=[hit.url for hit in hits],
                    expires_at=(
                        now + timedelta(hours=filters.cache_ttl_hours)
                    ),
                )
                self.session.add(cached_search)
            else:
                cached_search.result_urls = [hit.url for hit in hits]
                cached_search.created_at = now
                cached_search.expires_at = (
                    now + timedelta(hours=filters.cache_ttl_hours)
                )
            self.session.commit()

        collected: list[tuple[SourceConfigModel, CollectedItem]] = []
        errors: list[dict[str, str]] = []
        for hit in hits[: filters.limit]:
            canonical_url = canonicalize_url(hit.url)
            cached_page = self.session.scalar(
                select(WebPageCacheModel).where(
                    WebPageCacheModel.canonical_url == canonical_url
                )
            )
            if (
                cached_page is not None
                and cached_page.status == "ready"
                and self._aware(cached_page.expires_at) > now
            ):
                page = CrawledPage(
                    url=cached_page.url,
                    title=cached_page.title,
                    excerpt=cached_page.excerpt,
                    content_text=cached_page.content_text,
                    published_at=cached_page.published_at,
                )
            else:
                try:
                    page = self.crawler.crawl(hit)
                except Exception as error:
                    errors.append(
                        {
                            "error_code": self._error_code(error),
                            "message": f"{hit.url}: {str(error)[:220]}",
                        }
                    )
                    continue
                digest = hashlib.sha256(
                    page.content_text.encode("utf-8")
                ).hexdigest()
                if cached_page is None:
                    cached_page = WebPageCacheModel(
                        canonical_url=canonical_url,
                        url=page.url,
                        title=page.title,
                        excerpt=page.excerpt,
                        content_text=page.content_text,
                        content_digest=digest,
                        published_at=page.published_at,
                        expires_at=(
                            now + timedelta(hours=filters.cache_ttl_hours)
                        ),
                    )
                    self.session.add(cached_page)
                else:
                    cached_page.url = page.url
                    cached_page.title = page.title
                    cached_page.excerpt = page.excerpt
                    cached_page.content_text = page.content_text
                    cached_page.content_digest = digest
                    cached_page.published_at = page.published_at
                    cached_page.status = "ready"
                    cached_page.error_code = None
                    cached_page.fetched_at = now
                    cached_page.expires_at = (
                        now + timedelta(hours=filters.cache_ttl_hours)
                    )
                self.session.commit()
            source = self._source_for(page.url)
            collected.append(
                (
                    source,
                    CollectedItem(
                        external_id=canonical_url,
                        title=page.title,
                        url=page.url,
                        description=(
                            page.excerpt or page.content_text[:1200]
                        ),
                        published_at=page.published_at or now,
                    ),
                )
            )

        run, information_ids = self.collection.ingest_discovered_items(
            collected,
            idempotency_key=idempotency_key,
            trigger_type="web_search",
        )
        status: Literal["completed", "partial", "failed"]
        if errors and information_ids:
            status = "partial"
        elif errors and not information_ids:
            status = "partial"
        else:
            status = "completed"
        return WebSearchCollectResult(
            status=status,
            summary=(
                f"联网搜索返回 {len(hits)} 个网址，成功抓取 "
                f"{len(collected)} 页，新增 {run.items_added} 条可检索信息。"
            ),
            provider=self.provider.provider_id,
            cache_hit=cache_hit,
            searched_count=len(hits),
            crawled_count=len(collected),
            added_count=run.items_added,
            information_ids=information_ids,
            errors=errors,
        )

    def _source_for(self, url: str) -> SourceConfigModel:
        hostname = (urlsplit(url).hostname or "unknown").lower()
        name = f"网络搜索 · {hostname}"
        source = self.session.scalar(
            select(SourceConfigModel).where(SourceConfigModel.name == name)
        )
        if source is None:
            source = SourceConfigModel(
                name=name,
                kind="web_search",
                config={"origin": hostname},
                enabled=False,
            )
            self.session.add(source)
            self.session.commit()
        return source

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _error_code(error: Exception) -> str:
        if str(error) == "WEB_CRAWL_ROBOTS_DENIED":
            return "WEB_CRAWL_ROBOTS_DENIED"
        if isinstance(error, httpx.TimeoutException):
            return "WEB_SEARCH_TIMEOUT"
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code == 429:
                return "WEB_SEARCH_RATE_LIMITED"
            return "WEB_SEARCH_HTTP_ERROR"
        return "WEB_SEARCH_FAILED"
