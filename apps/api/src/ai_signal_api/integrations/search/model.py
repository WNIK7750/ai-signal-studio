from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

import httpx

from ai_signal_api.integrations.search.brave import SearchHit
from ai_signal_api.modules.models.service import ResolvedModel


class SearchProvider(Protocol):
    provider_id: str

    def search(
        self,
        query: str,
        *,
        count: int,
        freshness: str | None,
    ) -> list[SearchHit]: ...


class ModelWebSearchProvider:
    """OpenAI-compatible Responses web-search adapter."""

    def __init__(
        self,
        model: ResolvedModel,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.model = model
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.provider_id = f"model:{model.id}"

    def search(
        self,
        query: str,
        *,
        count: int,
        freshness: str | None,
    ) -> list[SearchHit]:
        if not self.model.api_key:
            raise ValueError("SEARCH_MODEL_NOT_CONFIGURED")
        recency = {
            "pd": "最近 24 小时",
            "pw": "最近一周",
            "pm": "最近一个月",
            "py": "最近一年",
        }.get(freshness, "尽可能新的")
        body = {
            "model": self.model.model_id,
            "input": (
                f"请联网搜索“{query}”，优先选择{recency}且可直接访问的"
                f"高质量来源，最多返回 {min(count, 20)} 个不同网页。"
            ),
            "tools": [{"type": "web_search"}],
        }
        headers = {
            "Authorization": f"Bearer {self.model.api_key}",
            "Content-Type": "application/json",
        }
        endpoint = self._responses_url(self.model.base_url)
        if self.client is not None:
            response = self.client.post(
                endpoint,
                headers=headers,
                json=body,
                timeout=self.timeout_seconds,
            )
        else:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(endpoint, headers=headers, json=body)
        response.raise_for_status()
        hits = self._hits(response.json(), limit=min(count, 20))
        if not hits:
            raise ValueError("SEARCH_MODEL_NO_CITATIONS")
        return hits

    @staticmethod
    def _responses_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        for suffix in ("/chat/completions", "/responses"):
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
        return f"{normalized}/responses"

    @classmethod
    def _hits(cls, payload: dict[str, Any], *, limit: int) -> list[SearchHit]:
        found: dict[str, SearchHit] = {}
        for output in payload.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if not isinstance(content, dict):
                    continue
                text = str(content.get("text") or "").strip()
                for annotation in content.get("annotations", []):
                    if not isinstance(annotation, dict):
                        continue
                    citation = annotation.get("url_citation", annotation)
                    if not isinstance(citation, dict):
                        continue
                    url = str(citation.get("url") or "").strip()
                    if not url or url in found:
                        continue
                    found[url] = SearchHit(
                        title=str(citation.get("title") or "联网搜索来源"),
                        url=url,
                        description=text[:1200],
                        published_at=cls._date(citation.get("published_at")),
                    )
                    if len(found) >= limit:
                        return list(found.values())
        return list(found.values())

    @staticmethod
    def _date(value: object) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None


class FallbackWebSearchProvider:
    """Try configured search providers in order without hiding all failures."""

    def __init__(self, providers: list[SearchProvider]) -> None:
        if not providers:
            raise ValueError("SEARCH_PROVIDER_REQUIRED")
        self.providers = providers
        self.provider_id = "fallback:" + ",".join(
            provider.provider_id for provider in providers
        )

    def search(
        self,
        query: str,
        *,
        count: int,
        freshness: str | None,
    ) -> list[SearchHit]:
        last_error: Exception | None = None
        for provider in self.providers:
            try:
                hits = provider.search(
                    query,
                    count=count,
                    freshness=freshness,
                )
                if hits:
                    return hits
            except Exception as error:  # provider boundary
                last_error = error
        if last_error is not None:
            raise last_error
        raise ValueError("SEARCH_PROVIDER_RETURNED_NO_RESULTS")
