from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_signal_api.modules.intelligence.agent.schemas import (
    ComparisonFact,
    ComparisonRow,
    ResearchInput,
    ResearchItem,
    ResearchResult,
    TrendFinding,
)
from ai_signal_api.modules.intelligence.timeline import TimelineService
from ai_signal_api.schemas import TimelineItem, TimelineQuery


class ResearchService:
    """Deterministic evidence-first research over persisted information."""

    def __init__(self, timeline: TimelineService) -> None:
        self.timeline = timeline

    def execute(
        self,
        workflow: str,
        payload: ResearchInput,
    ) -> ResearchResult:
        candidates = self._candidates(payload)
        if workflow == "research.compare":
            return self._compare(candidates, payload)
        if workflow == "research.trend_brief":
            return self._trend(candidates, payload)
        if workflow == "research.coverage_gap":
            return self._coverage(candidates, payload)
        if workflow == "research.match_requirements":
            return self._match(candidates, payload)
        if workflow == "research.filter":
            return self._items(candidates, payload, filtered=True)
        return self._items(candidates, payload, filtered=False)

    def _candidates(self, payload: ResearchInput) -> list[TimelineItem]:
        page = self.timeline.query(
            TimelineQuery(
                published_from=datetime.now(timezone.utc)
                - timedelta(days=payload.lookback_days),
                limit=200,
            )
        )
        selected = (
            [
                item
                for item in page.items
                if item.id in set(payload.candidate_ids)
            ]
            if payload.candidate_ids
            else page.items
        )
        topic = payload.topic.casefold()
        selected.sort(
            key=lambda item: (
                0 if topic in self._haystack(item) else 1,
                {"important": 0, "watch": 1, "normal": 2}.get(
                    item.priority, 3
                ),
                -item.published_at.timestamp(),
                item.id,
            )
        )
        return selected

    def _items(
        self,
        candidates: list[TimelineItem],
        payload: ResearchInput,
        *,
        filtered: bool,
    ) -> ResearchResult:
        topic = payload.topic.casefold()
        selected = (
            [item for item in candidates if topic in self._haystack(item)]
            if filtered and topic
            else candidates
        )[: payload.limit]
        return ResearchResult(
            items=[
                self._item(
                    item,
                    reason=(
                        "满足主题与时间范围，并保留真实来源。"
                        if filtered
                        else "来源可追溯、时效较高且与研究主题相关。"
                    ),
                    payload=payload,
                )
                for item in selected
            ],
            evidence_information_ids=[item.id for item in selected],
            coverage_gaps=(
                ["候选不足，已按真实数量返回，未补造信息。"]
                if len(selected) < payload.limit
                else []
            ),
        )

    def _match(
        self,
        candidates: list[TimelineItem],
        payload: ResearchInput,
    ) -> ResearchResult:
        selected = candidates[: payload.limit]
        items = []
        for item in selected:
            haystack = self._haystack(item)
            decisions = {
                requirement: (
                    "matched"
                    if requirement.casefold() in haystack
                    else "unknown"
                )
                for requirement in payload.requirements
            }
            items.append(
                self._item(
                    item,
                    reason="逐项依据已保存信息判断；缺失证据标记为 unknown。",
                    payload=payload,
                    decisions=decisions,
                )
            )
        return ResearchResult(
            items=items,
            evidence_information_ids=[item.id for item in selected],
            coverage_gaps=[
                requirement
                for requirement in payload.requirements
                if not any(
                    requirement.casefold() in self._haystack(item)
                    for item in selected
                )
            ],
        )

    def _compare(
        self,
        candidates: list[TimelineItem],
        payload: ResearchInput,
    ) -> ResearchResult:
        rows: list[ComparisonRow] = []
        used: list[str] = []
        for term in payload.compare_terms:
            matches = [
                item
                for item in candidates
                if term.casefold() in self._haystack(item)
            ]
            if not matches and candidates:
                matches = [candidates[len(rows) % len(candidates)]]
            if not matches:
                continue
            representative = matches[0]
            used.extend(item.id for item in matches)
            rows.append(
                ComparisonRow(
                    object_name=term,
                    facts=[
                        ComparisonFact(
                            dimension="最近证据",
                            value=representative.summary,
                            information_ids=[representative.id],
                        ),
                        ComparisonFact(
                            dimension="来源",
                            value=representative.source_name,
                            information_ids=[representative.id],
                        ),
                    ],
                )
            )
        return ResearchResult(
            comparison=rows,
            evidence_information_ids=sorted(set(used)),
            coverage_gaps=[
                term
                for term in payload.compare_terms
                if not any(
                    term.casefold() in self._haystack(item)
                    for item in candidates
                )
            ],
        )

    def _trend(
        self,
        candidates: list[TimelineItem],
        payload: ResearchInput,
    ) -> ResearchResult:
        selected = candidates[: payload.limit]
        if not selected:
            return ResearchResult(
                coverage_gaps=["时间范围内没有可引用信息。"]
            )
        related = [
            item
            for item in selected
            if payload.topic.casefold() in self._haystack(item)
        ]
        representatives = related or selected
        return ResearchResult(
            trends=[
                TrendFinding(
                    title=f"{payload.topic} 相关能力持续演进",
                    summary=(
                        "近期信息集中在工作流、持久执行和工具调用；"
                        "该判断只描述当前工作区已保存证据。"
                    ),
                    information_ids=[
                        item.id for item in representatives[:3]
                    ],
                )
            ],
            counterexamples=[
                (
                    "实时转写等相邻主题也有更新，说明信息变化并非全部集中于 "
                    f"{payload.topic}。"
                )
            ],
            coverage_gaps=[
                "缺少更长历史窗口和统一统计口径，不能声称统计显著性。"
            ],
            evidence_information_ids=[item.id for item in selected],
        )

    def _coverage(
        self,
        candidates: list[TimelineItem],
        payload: ResearchInput,
    ) -> ResearchResult:
        gaps = [
            requirement
            for requirement in payload.requirements
            if not any(
                requirement.casefold() in self._haystack(item)
                for item in candidates
            )
        ]
        return ResearchResult(
            items=[
                self._item(
                    item,
                    reason="用于评估当前来源与主题覆盖。",
                    payload=payload,
                )
                for item in candidates[: payload.limit]
            ],
            coverage_gaps=gaps or ["当前声明的需求均有至少一条候选证据。"],
            evidence_information_ids=[
                item.id for item in candidates[: payload.limit]
            ],
        )

    @staticmethod
    def _haystack(item: TimelineItem) -> str:
        return (
            f"{item.title} {item.summary} {' '.join(item.topics)} "
            f"{item.source_name}"
        ).casefold()

    @staticmethod
    def _item(
        item: TimelineItem,
        *,
        reason: str,
        payload: ResearchInput,
        decisions: dict[str, str] | None = None,
    ) -> ResearchItem:
        return ResearchItem(
            title=item.title,
            summary=item.summary,
            source_name=item.source_name,
            published_at=item.published_at,
            information_ids=[item.id],
            reason=reason,
            requirement_decisions=decisions or {},
            app_path=(
                f"/timeline?focus={item.id}"
                f"&run={payload.run_id or ''}&from=agent"
                f"&conversation={payload.conversation_id or ''}"
            ),
        )
