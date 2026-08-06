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
    limit: int = Field(default=5, ge=1, le=20)
    requirements: list[str] = Field(default_factory=list, max_length=12)
    compare_terms: list[str] = Field(default_factory=list, max_length=5)
    candidate_ids: list[str] = Field(default_factory=list, max_length=200)
    run_id: str | None = None
    conversation_id: str | None = None


class ResearchItem(BaseModel):
    title: str
    summary: str
    source_name: str
    published_at: datetime
    information_ids: list[str] = Field(min_length=1)
    reason: str
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


class ResearchResult(BaseModel):
    status: Literal["completed", "partial"] = "completed"
    items: list[ResearchItem] = Field(default_factory=list)
    comparison: list[ComparisonRow] = Field(default_factory=list)
    trends: list[TrendFinding] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)
    evidence_information_ids: list[str] = Field(default_factory=list)
