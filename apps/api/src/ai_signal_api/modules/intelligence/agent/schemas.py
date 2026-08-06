from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class InformationRecommendInput(BaseModel):
    candidate_ids: list[str] = Field(default_factory=list, max_length=200)
    topic: str = Field(default="Agent", max_length=120)
    limit: int = Field(default=5, ge=1, le=10)
    run_id: str | None = None
    conversation_id: str | None = None


class InformationRecommendation(BaseModel):
    information_id: str
    color: str
    title: str
    quick_summary: str = Field(min_length=100, max_length=400)
    source_id: str
    source_name: str
    source_url: str
    published_at: datetime
    reason: str
    app_path: str


class InformationRecommendResult(BaseModel):
    status: str = "completed"
    items: list[InformationRecommendation]


class ResearchInput(BaseModel):
    topic: str = Field(default="Agent", max_length=120)
    lookback_days: int = Field(default=30, ge=1, le=365)
    lookback_hours: int | None = Field(default=None, ge=1, le=24 * 365)
    fallback_lookback_hours: int | None = Field(
        default=None,
        ge=1,
        le=24 * 365,
    )
    allow_workspace_backfill: bool = False
    published_from: datetime | None = None
    published_to: datetime | None = None
    limit: int = Field(default=5, ge=1, le=20)
    rank_by: Literal["impact", "relevance", "recency"] = "impact"
    requirements: list[str] = Field(default_factory=list, max_length=12)
    compare_terms: list[str] = Field(default_factory=list, max_length=5)
    candidate_ids: list[str] = Field(default_factory=list, max_length=200)
    run_id: str | None = None
    conversation_id: str | None = None
    user_goal: str = Field(default="", max_length=1000)
    evidence_excerpts: list[str] = Field(default_factory=list, max_length=20)
    output_max_chars: int = Field(default=1600, ge=200, le=6000)


class ResearchItem(BaseModel):
    information_id: str
    color: Literal["important", "watch", "normal"]
    title: str
    summary: str
    source_id: str
    source_name: str
    source_url: str
    published_at: datetime
    information_ids: list[str] = Field(min_length=1)
    reason: str
    ranking_basis: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list, max_length=6)
    requirement_decisions: dict[
        str, Literal["matched", "unknown", "rejected"]
    ] = Field(default_factory=dict)
    app_path: str


class ComparisonFact(BaseModel):
    dimension: str
    value: str
    information_ids: list[str] = Field(min_length=1)


class ComparisonRow(BaseModel):
    object_name: str
    facts: list[ComparisonFact] = Field(min_length=1)


class TrendFinding(BaseModel):
    title: str
    summary: str
    information_ids: list[str] = Field(min_length=1)


class TrendSynthesis(BaseModel):
    overview: str
    key_findings: list[TrendFinding] = Field(default_factory=list)
    why_it_matters: list[TrendFinding] = Field(default_factory=list)
    differences: list[TrendFinding] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    information_ids: list[str] = Field(default_factory=list)
    synthesis_mode: Literal["model", "deterministic"] = "deterministic"


class RecommendationDecision(BaseModel):
    information_id: str
    reason: str = Field(min_length=1, max_length=600)
    priority: Literal["important", "watch", "normal"] | None = None
    tags: list[str] = Field(default_factory=list, max_length=6)


class ResearchAnalysisSynthesis(BaseModel):
    recommendation_overview: str = Field(min_length=1, max_length=1200)
    recommendations: list[RecommendationDecision] = Field(
        default_factory=list,
        max_length=20,
    )
    uncertainties: list[str] = Field(default_factory=list, max_length=12)
    trend: TrendSynthesis


class ResearchResult(BaseModel):
    status: Literal["completed", "partial"] = "completed"
    items: list[ResearchItem] = Field(default_factory=list)
    comparison: list[ComparisonRow] = Field(default_factory=list)
    trends: list[TrendFinding] = Field(default_factory=list)
    synthesis: TrendSynthesis | None = None
    counterexamples: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    evidence_information_ids: list[str] = Field(default_factory=list)
    requested_item_count: int = 0
    effective_lookback_hours: int | None = None
    backfilled_information_ids: list[str] = Field(default_factory=list)
