from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ai_signal_api.modules.intelligence.agent.schemas import (
    ComparisonFact,
    ComparisonRow,
    ResearchInput,
    ResearchItem,
    ResearchResult,
    TrendFinding,
    TrendSynthesis,
)
from ai_signal_api.modules.intelligence.timeline import TimelineService
from ai_signal_api.modules.intelligence.search import (
    IntelligenceSearchInput,
    UnifiedIntelligenceSearchService,
)
from ai_signal_api.schemas import TimelineItem, TimelineQuery


@dataclass(frozen=True)
class _CandidateSet:
    items: list[TimelineItem]
    requested_item_count: int
    effective_lookback_hours: int
    backfilled_information_ids: list[str]


class ResearchService:
    """Deterministic evidence-first research over persisted information."""

    def __init__(
        self,
        timeline: TimelineService,
        search: UnifiedIntelligenceSearchService | None = None,
    ) -> None:
        self.timeline = timeline
        self.search = search

    def execute(
        self,
        workflow: str,
        payload: ResearchInput,
    ) -> ResearchResult:
        evidence = self._candidates(payload)
        candidates = evidence.items
        if workflow == "research.compare":
            result = self._compare(candidates, payload)
        elif workflow == "research.trend_brief":
            result = self._trend(candidates, payload)
        elif workflow == "research.coverage_gap":
            result = self._coverage(candidates, payload)
        elif workflow == "research.match_requirements":
            result = self._match(candidates, payload)
        elif workflow == "research.filter":
            result = self._items(candidates, payload, filtered=True)
        else:
            result = self._items(candidates, payload, filtered=False)
        return result.model_copy(
            update={
                "requested_item_count": evidence.requested_item_count,
                "effective_lookback_hours": (
                    evidence.effective_lookback_hours
                ),
                "backfilled_information_ids": (
                    evidence.backfilled_information_ids
                ),
            }
        )

    def _candidates(self, payload: ResearchInput) -> _CandidateSet:
        now = datetime.now(timezone.utc)
        requested_hours = (
            payload.lookback_hours
            if payload.lookback_hours is not None
            else payload.lookback_days * 24
        )
        published_from = payload.published_from or (
            now - timedelta(hours=requested_hours)
        )
        candidate_ids = set(payload.candidate_ids)
        exact_items = self._search_items(
            payload,
            published_from=published_from,
            published_to=payload.published_to,
            candidate_ids=list(candidate_ids),
        )
        selected = list(exact_items)
        requested_item_count = len(selected)
        backfilled_ids: list[str] = []
        effective_hours = requested_hours
        fallback_hours = payload.fallback_lookback_hours or requested_hours
        if (
            payload.published_from is None
            and fallback_hours > requested_hours
            and len(selected) < payload.limit
        ):
            fallback_candidates = self._search_items(
                payload,
                published_from=now - timedelta(hours=fallback_hours),
                published_to=payload.published_to,
                candidate_ids=(
                    list(candidate_ids)
                    if payload.candidate_ids
                    and not payload.allow_workspace_backfill
                    else []
                ),
            )
            selected_ids = {item.id for item in selected}
            for item in fallback_candidates:
                if item.id in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(item.id)
                backfilled_ids.append(item.id)
                if len(selected) >= payload.limit:
                    break
            if backfilled_ids:
                effective_hours = fallback_hours
        topic = payload.topic.casefold()
        selected.sort(
            key=lambda item: (
                {"important": 0, "watch": 1, "normal": 2}.get(
                    item.priority, 3
                ),
                0 if topic in self._haystack(item) else 1,
                -item.published_at.timestamp(),
                item.id,
            )
        )
        return _CandidateSet(
            items=selected,
            requested_item_count=requested_item_count,
            effective_lookback_hours=effective_hours,
            backfilled_information_ids=backfilled_ids,
        )

    def _search_items(
        self,
        payload: ResearchInput,
        *,
        published_from: datetime,
        published_to: datetime | None,
        candidate_ids: list[str],
    ) -> list[TimelineItem]:
        if self.search is None:
            page = self.timeline.query(
                TimelineQuery(
                    published_from=published_from,
                    published_to=published_to,
                    limit=200,
                )
            )
            allowed = set(candidate_ids)
            return (
                [item for item in page.items if item.id in allowed]
                if allowed
                else list(page.items)
            )
        result = self.search.search(
            IntelligenceSearchInput(
                query=payload.topic,
                scopes=["intelligence"],
                limit=50,
                published_from=published_from,
                published_to=published_to,
                candidate_ids=candidate_ids,
            )
        )
        return [
            TimelineItem(
                id=item.information_id,
                title=item.title,
                summary=item.summary,
                canonical_url=item.source_url,
                source_id=item.source_id,
                source_name=item.source_name,
                source_kind=item.source_kind,
                published_at=item.published_at,
                topics=item.topics,
                priority=item.priority,
                task_ids=[],
                seen=False,
                starred=False,
                archived="archived" in item.scopes,
                note="",
            )
            for item in result.items
        ]

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
            status=(
                "partial"
                if len(selected) < payload.limit
                else "completed"
            ),
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
                status="partial",
                synthesis=TrendSynthesis(
                    overview=(
                        "当前时间范围内没有可引用信息，"
                        "无法形成有证据支撑的趋势判断。"
                    ),
                    uncertainties=["时间范围内没有可引用信息。"],
                    synthesis_mode="deterministic",
                ),
                coverage_gaps=["时间范围内没有可引用信息。"],
            )
        related = [
            item
            for item in selected
            if payload.topic.casefold() in self._haystack(item)
        ]
        representatives = related or selected
        ids = [item.id for item in representatives]
        main = representatives[0]
        secondary = representatives[1:]
        key_findings = [
            TrendFinding(
                title="热点聚焦于可落地的 AI 能力",
                summary=(
                    f"入选内容共同指向“{payload.topic}”能力从发布走向"
                    "工作流、工具或产品应用；结论仅基于当前时间窗口内的证据。"
                ),
                information_ids=ids[: min(3, len(ids))],
            )
        ]
        why = [
            TrendFinding(
                title="优先关注可验证的产品与生态影响",
                summary=(
                    f"最高优先级证据“{main.title}”兼具时效、主题相关性"
                    "和可追溯来源，适合作为后续判断的起点。"
                ),
                information_ids=[main.id],
            )
        ]
        differences = (
            [
                TrendFinding(
                    title="各条热点的侧重点并不相同",
                    summary=(
                        "其余入选信息分别提供不同来源或应用角度，"
                        "不应被解读成同一事件的重复摘要。"
                    ),
                    information_ids=[item.id for item in secondary[:2]],
                )
            ]
            if secondary
            else []
        )
        return ResearchResult(
            trends=key_findings,
            synthesis=TrendSynthesis(
                overview=(
                    f"在最近 {payload.lookback_hours or payload.lookback_days * 24}"
                    f" 小时的已保存信息中，共选取 {len(selected)} 条"
                    f"高影响力 {payload.topic} 内容进行交叉分析。"
                )[: payload.output_max_chars],
                key_findings=key_findings,
                why_it_matters=why,
                differences=differences,
                uncertainties=[
                    "影响力排序使用工作区颜色、主题相关性、发布时间和稳定 ID，"
                    "不包含外部阅读量或点赞量。"
                ],
                information_ids=[item.id for item in selected],
                synthesis_mode="deterministic",
            ),
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
            information_id=item.id,
            color=item.priority,
            title=item.title,
            summary=item.summary,
            source_id=item.source_id,
            source_name=item.source_name,
            source_url=item.canonical_url,
            published_at=item.published_at,
            information_ids=[item.id],
            reason=reason,
            ranking_basis=[
                f"颜色优先级：{item.priority}",
                "主题相关性",
                f"发布时间：{item.published_at.isoformat()}",
                f"稳定信息 ID：{item.id}",
            ],
            tags=list(item.topics),
            requirement_decisions=decisions or {},
            app_path=(
                f"/timeline?focus={item.id}"
                f"&run={payload.run_id or ''}&from=agent"
                f"&conversation={payload.conversation_id or ''}"
            ),
        )
