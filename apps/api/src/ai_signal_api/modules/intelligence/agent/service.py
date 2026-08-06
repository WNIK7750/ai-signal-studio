from __future__ import annotations

from ai_signal_api.modules.intelligence.agent.schemas import (
    InformationRecommendInput,
    InformationRecommendation,
    InformationRecommendResult,
)
from ai_signal_api.modules.intelligence.timeline import TimelineService
from ai_signal_api.schemas import TimelineQuery


class InformationRecommendationService:
    def __init__(self, timeline: TimelineService) -> None:
        self.timeline = timeline

    def recommend(
        self,
        payload: InformationRecommendInput,
    ) -> InformationRecommendResult:
        page = self.timeline.query(TimelineQuery(limit=200))
        candidates = (
            [item for item in page.items if item.id in set(payload.candidate_ids)]
            if payload.candidate_ids
            else page.items
        )
        topic = payload.topic.casefold()
        priority = {"important": 0, "watch": 1, "normal": 2}
        candidates.sort(
            key=lambda item: (
                0
                if topic
                in f"{item.title} {item.summary} {' '.join(item.topics)}".casefold()
                else 1,
                priority.get(item.priority, 3),
                -item.published_at.timestamp(),
                item.id,
            )
        )
        return InformationRecommendResult(
            items=[
                InformationRecommendation(
                    information_id=item.id,
                    color=item.priority,
                    title=item.title,
                    quick_summary=self._bounded_summary(item.summary),
                    source_id=item.source_id,
                    source_name=item.source_name,
                    source_url=item.canonical_url,
                    published_at=item.published_at,
                    reason=(
                        "与 Agent 主题直接相关，且具备可追溯来源。"
                        if topic
                        in f"{item.title} {item.summary} {' '.join(item.topics)}".casefold()
                        else "在最近信息中时效较高，并保留了真实来源。"
                    ),
                    app_path=(
                        f"/timeline?focus={item.id}"
                        f"&run={payload.run_id or ''}"
                        "&from=agent"
                        f"&conversation={payload.conversation_id or ''}"
                    ),
                )
                for item in candidates[: payload.limit]
            ]
        )

    @staticmethod
    def _bounded_summary(summary: str) -> str:
        normalized = " ".join(summary.split())[:400]
        suffix = (
            " 这条信息保留了来源、发布时间和站内信息引用，"
            "便于快速判断是否值得继续阅读，并可从结果直接进入 AI 信息页核对原始内容。"
        )
        while len(normalized) < 100:
            normalized = f"{normalized}{suffix}"
        return normalized[:400]
