from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

import httpx
from dateutil.parser import parse as parse_datetime


@dataclass(frozen=True, slots=True)
class SearchHit:
    title: str
    url: str
    description: str
    published_at: datetime | None = None


class WebSearchProvider(Protocol):
    provider_id: str

    def search(
        self,
        query: str,
        *,
        count: int,
        freshness: str | None,
    ) -> list[SearchHit]: ...


class BraveWebSearchProvider:
    provider_id = "brave"

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = "https://api.search.brave.com/res/v1",
    ) -> None:
        self.api_key = api_key
        self.client = client
        self.base_url = base_url.rstrip("/")

    def search(
        self,
        query: str,
        *,
        count: int,
        freshness: str | None,
    ) -> list[SearchHit]:
        params: dict[str, str | int] = {
            "q": query,
            "count": min(count, 20),
            "search_lang": "zh-hans",
            "safesearch": "moderate",
            "extra_snippets": "true",
        }
        if freshness:
            params["freshness"] = freshness
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        if self.client is not None:
            response = self.client.get(
                f"{self.base_url}/web/search",
                params=params,
                headers=headers,
                timeout=20,
            )
        else:
            with httpx.Client(timeout=20) as client:
                response = client.get(
                    f"{self.base_url}/web/search",
                    params=params,
                    headers=headers,
                )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("web", {}).get("results", [])
        return [
            SearchHit(
                title=str(item.get("title") or "未命名网页"),
                url=str(item["url"]),
                description=" ".join(
                    [
                        str(item.get("description") or ""),
                        *[
                            str(value)
                            for value in item.get("extra_snippets", [])
                        ],
                    ]
                ).strip(),
                published_at=self._date(
                    item.get("page_age") or item.get("age")
                ),
            )
            for item in results
            if item.get("url")
        ]

    @staticmethod
    def _date(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            parsed = parse_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
