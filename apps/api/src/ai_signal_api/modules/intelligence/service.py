from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ai_signal_api.modules.collection.collectors import CollectedItem


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    summary: str
    topics: list[str]
    priority: str


class Analyzer(Protocol):
    def analyze(self, item: CollectedItem) -> AnalysisResult: ...


class HeuristicAnalyzer:
    """Offline-first analyzer used until a configured LLM adapter is present."""

    topic_terms = {
        "Agent": ("agent", "智能体"),
        "AI Coding": ("coding", "代码", "编程"),
        "LangGraph": ("langgraph", "graph"),
        "实时转写": ("转写", "whisper", "websocket"),
        "模型与工具": ("模型", "tool", "工具"),
    }

    def analyze(self, item: CollectedItem) -> AnalysisResult:
        combined = f"{item.title} {item.description}".lower()
        topics = [
            topic
            for topic, terms in self.topic_terms.items()
            if any(term in combined for term in terms)
        ][:2]
        if not topics:
            topics = ["AI 信息"]

        if any(term in combined for term in ("openai", "langgraph", "重大")):
            priority = "important"
        elif any(
            term in combined
            for term in ("release", "更新", "开源", "whisper")
        ):
            priority = "watch"
        else:
            priority = "normal"

        summary = re.sub(r"\s+", " ", item.description).strip()
        if len(summary) > 100:
            summary = f"{summary[:99].rstrip()}…"
        if not summary:
            summary = "来源未提供摘要。"

        return AnalysisResult(
            summary=summary,
            topics=topics,
            priority=priority,
        )
