from __future__ import annotations

import re
import ipaddress
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import urljoin, urlsplit

import feedparser
import httpx
from dateutil.parser import parse as parse_datetime


@dataclass(frozen=True, slots=True)
class CollectedItem:
    external_id: str | None
    title: str
    url: str
    description: str
    published_at: datetime


class Collector(Protocol):
    def collect(self, config: dict[str, Any]) -> list[CollectedItem]: ...


def _as_utc(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback
    parsed = parse_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _plain_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def validate_public_url(url: str) -> str:
    parts = urlsplit(url)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
    ):
        raise ValueError("SOURCE_URL_UNSAFE")
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                parts.hostname,
                parts.port or (443 if parts.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as error:
        raise httpx.ConnectError("SOURCE_DNS_FAILED") from error
    if not addresses:
        raise httpx.ConnectError("SOURCE_DNS_FAILED")
    for address in addresses:
        candidate = ipaddress.ip_address(address)
        if not candidate.is_global:
            raise ValueError("SOURCE_URL_PRIVATE_ADDRESS")
    return url


class SafeHttpClient:
    def __init__(
        self,
        *,
        max_bytes: int = 2_000_000,
        max_redirects: int = 3,
    ) -> None:
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        allowed_types: tuple[str, ...],
    ) -> httpx.Response:
        current = url
        with httpx.Client(timeout=15, follow_redirects=False) as client:
            for redirect_count in range(self.max_redirects + 1):
                validate_public_url(current)
                response = client.get(
                    current,
                    headers=headers,
                    params=params if redirect_count == 0 else None,
                )
                if response.is_redirect:
                    if redirect_count >= self.max_redirects:
                        raise ValueError("SOURCE_REDIRECT_LIMIT")
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("SOURCE_REDIRECT_INVALID")
                    current = urljoin(str(response.url), location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get(
                    "content-type",
                    "",
                ).lower()
                if not any(
                    content_type.startswith(value)
                    for value in allowed_types
                ):
                    raise ValueError("SOURCE_CONTENT_TYPE_UNSUPPORTED")
                if len(response.content) > self.max_bytes:
                    raise ValueError("SOURCE_RESPONSE_TOO_LARGE")
                return response
        raise ValueError("SOURCE_REDIRECT_LIMIT")


class DemoCollector:
    def __init__(self, now: datetime | None = None) -> None:
        self.now = now or datetime.now(timezone.utc)

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        dataset = config.get("dataset", "openai")
        items = {
            "openai": CollectedItem(
                external_id="openai-agent-workflows",
                title="OpenAI 发布新的 Agent 工作流能力",
                url="https://openai.com/index/agent-workflows?utm_source=demo",
                description=(
                    "引入可视化编排与多步骤工具调用，提升复杂任务的"
                    "可靠性与可控性。"
                ),
                published_at=self.now - timedelta(hours=2),
            ),
            "langgraph": CollectedItem(
                external_id="langgraph-persistence",
                title="LangGraph 增强持久化与恢复机制",
                url="https://blog.langchain.dev/langgraph-persistence/",
                description=(
                    "新增断点续跑与状态快照能力，适合需要恢复的长期任务。"
                ),
                published_at=self.now - timedelta(hours=4),
            ),
            "whisperlive": CollectedItem(
                external_id="whisperlive-websocket",
                title="开源实时转写工具更新 WebSocket 流式接口",
                url="https://github.com/collabora/WhisperLive/releases/tag/v0.2",
                description=(
                    "优化消息分段与心跳机制，改善弱网环境下的稳定性。"
                ),
                published_at=self.now - timedelta(hours=7),
            ),
        }
        return [items.get(dataset, items["openai"])]


class RssCollector:
    def __init__(self, client: SafeHttpClient | None = None) -> None:
        self.client = client or SafeHttpClient()

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        url = str(config["url"])
        limit = min(int(config.get("limit", 20)), 50)
        response = self.client.get(
            url,
            headers={"User-Agent": "AI-Signal-Studio/0.1"},
            allowed_types=(
                "application/rss+xml",
                "application/atom+xml",
                "application/xml",
                "text/xml",
            ),
        )
        feed = feedparser.parse(response.content)
        now = datetime.now(timezone.utc)
        return [
            CollectedItem(
                external_id=str(entry.get("id") or entry.get("link") or ""),
                title=_plain_text(str(entry.get("title", "未命名信息"))),
                url=str(entry.get("link", url)),
                description=_plain_text(
                    str(entry.get("summary") or entry.get("description") or "")
                ),
                published_at=_as_utc(
                    entry.get("published") or entry.get("updated"),
                    now,
                ),
            )
            for entry in feed.entries[:limit]
            if entry.get("link")
        ]


class GithubReleasesCollector:
    def __init__(self, client: SafeHttpClient | None = None) -> None:
        self.client = client or SafeHttpClient()

    def collect(self, config: dict[str, Any]) -> list[CollectedItem]:
        repository = str(config["repository"])
        limit = min(int(config.get("limit", 10)), 30)
        response = self.client.get(
            f"https://api.github.com/repos/{repository}/releases",
            params={"per_page": limit},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "AI-Signal-Studio/0.1",
            },
            allowed_types=("application/json",),
        )
        now = datetime.now(timezone.utc)
        return [
            CollectedItem(
                external_id=str(release.get("id")),
                title=str(
                    release.get("name")
                    or release.get("tag_name")
                    or "未命名 Release"
                ),
                url=str(release["html_url"]),
                description=_plain_text(str(release.get("body") or "")),
                published_at=_as_utc(
                    release.get("published_at")
                    or release.get("created_at"),
                    now,
                ),
            )
            for release in response.json()
            if release.get("html_url")
        ]


class CollectorRegistry:
    def __init__(self, demo_now: datetime | None = None) -> None:
        self._collectors: dict[str, Collector] = {
            "demo": DemoCollector(now=demo_now),
            "rss": RssCollector(),
            "github_releases": GithubReleasesCollector(),
        }

    def resolve(self, kind: str) -> Collector:
        try:
            return self._collectors[kind]
        except KeyError as error:
            raise ValueError(f"Unsupported source kind: {kind}") from error
