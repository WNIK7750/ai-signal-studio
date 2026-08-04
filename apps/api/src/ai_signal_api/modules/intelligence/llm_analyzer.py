from __future__ import annotations

import json
from typing import Literal

import httpx
from pydantic import BaseModel, Field, field_validator

from ai_signal_api.config import Settings
from ai_signal_api.integrations.llm.config import (
    LLMRuntimeConfig,
    resolve_llm_runtime,
)
from ai_signal_api.modules.collection.collectors import CollectedItem
from ai_signal_api.modules.intelligence.service import (
    AnalysisResult,
    Analyzer,
    HeuristicAnalyzer,
)


SYSTEM_PROMPT = (
    "你是 AI 信息分析器。只返回 JSON，字段为 summary、"
    "topics、priority。priority 只能是 important、watch、normal。"
)


class LLMAnalysisPayload(BaseModel):
    summary: str = Field(min_length=1, max_length=200)
    topics: list[str] = Field(min_length=1, max_length=3)
    priority: Literal["important", "watch", "normal"]

    @field_validator("summary")
    @classmethod
    def normalize_summary(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        normalized = [
            topic.strip()
            for topic in value
            if topic.strip()
        ]
        if not normalized:
            raise ValueError("topics must contain at least one value")
        return list(dict.fromkeys(normalized))[:3]


class OpenAICompatibleAnalyzer:
    def __init__(
        self,
        runtime: LLMRuntimeConfig,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.runtime = runtime
        self.client = client

    def analyze(self, item: CollectedItem) -> AnalysisResult:
        request_body = {
            "model": self.runtime.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"标题：{item.title}\n"
                        f"原始摘要：{item.description}"
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": self.runtime.max_output_tokens,
        }
        headers = {
            "Authorization": (
                "Bearer "
                f"{self.runtime.api_key.get_secret_value()}"
            ),
            "Content-Type": "application/json",
        }

        if self.client is not None:
            response = self.client.post(
                f"{self.runtime.base_url}/chat/completions",
                headers=headers,
                json=request_body,
                timeout=self.runtime.timeout_seconds,
            )
        else:
            with httpx.Client(
                timeout=self.runtime.timeout_seconds
            ) as client:
                response = client.post(
                    f"{self.runtime.base_url}/chat/completions",
                    headers=headers,
                    json=request_body,
                )
        response.raise_for_status()
        response_body = response.json()
        try:
            content = response_body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("LLM_RESPONSE_SHAPE_INVALID") from error
        if not isinstance(content, str):
            raise ValueError("LLM_RESPONSE_CONTENT_INVALID")

        payload = LLMAnalysisPayload.model_validate(
            json.loads(content)
        )
        return AnalysisResult(
            summary=payload.summary,
            topics=payload.topics,
            priority=payload.priority,
        )


def build_analyzer(settings: Settings) -> Analyzer:
    runtime = resolve_llm_runtime(settings)
    if runtime is None:
        return HeuristicAnalyzer()
    return OpenAICompatibleAnalyzer(runtime)
