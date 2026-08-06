from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


TurnStatus = Literal[
    "queued",
    "running",
    "waiting_input",
    "waiting_approval",
    "complete",
    "partial",
    "failed",
    "cancelled",
]


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    source: Literal["input", "business", "provider", "capability", "system"]
    retryable: bool = False
    user_action: str | None = None
    partial: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class EvidenceRef(BaseModel):
    evidence_id: str
    business_object_id: str
    source_id: str
    source_url: str
    captured_at: datetime
    title: str
    excerpt: str = Field(max_length=400)
    content_hash: str
    freshness: str


class AgentResultBlock(BaseModel):
    block_id: str
    type: Literal[
        "plan_summary",
        "signal_preview",
        "collection_summary",
        "information_list",
        "recommendation_list",
        "comparison_table",
        "trend_summary",
        "evidence_sources",
        "artifact_list",
        "partial_failure",
        "navigation_action",
    ]
    title: str
    data: dict[str, Any]


class AcceptancePolicy(BaseModel):
    id: Literal[
        "information_results.v1",
        "capability_effect.v1",
        "artifact_created.v1",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step_id: str
    title: str
    goal: str
    kind: Literal["capability", "domain_agent", "domain_workflow"]
    domains: list[str] = Field(min_length=1, max_length=3)
    capability_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    success_criteria: str
    acceptance_policy: AcceptancePolicy
    side_effect: Literal["read", "write", "external"]
    risk: Literal["low", "medium", "high"] = "low"
    failure_policy: Literal[
        "stop_dependents",
        "continue_independent",
        "retry_then_continue",
    ] = "stop_dependents"


class AgentPlan(BaseModel):
    objective: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)
    planning_mode: Literal["direct", "fast", "dynamic"]
    selected_domains: list[str] = Field(max_length=3)
    steps: list[PlanStep] = Field(min_length=1, max_length=5)
    max_replans: int = Field(default=2, ge=0, le=2)

    @model_validator(mode="after")
    def validate_dag(self) -> AgentPlan:
        ids = [step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("AGENT_PLAN_STEP_DUPLICATE")
        known = set(ids)
        for step in self.steps:
            if step.step_id in step.dependencies or any(
                dependency not in known for dependency in step.dependencies
            ):
                raise ValueError("AGENT_PLAN_DEPENDENCY_INVALID")
        graph = {
            step.step_id: set(step.dependencies) for step in self.steps
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("AGENT_PLAN_DEPENDENCY_CYCLE")
            if step_id in visited:
                return
            visiting.add(step_id)
            for dependency in graph[step_id]:
                visit(dependency)
            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in ids:
            visit(step_id)
        return self


class ActionEnvelope(BaseModel):
    turn_id: str
    step_id: str
    domain_id: str
    capability_id: str
    canonical_input: dict[str, Any]
    input_digest: str
    acceptance_policy: AcceptancePolicy
    side_effect: str
    risk: str


class ExecutionManifest(BaseModel):
    workflow_version: str = "0.4.0"
    state_schema_version: str = "1.0.0"
    plan_schema_version: str = "1.0.0"
    event_schema_version: str = "1.0.0"
    base_prompt_version: str = "base-prompt@1.0.0"
    domain_pack_versions: dict[str, str] = Field(default_factory=dict)
    tool_catalog_version: str = "1"
    model_config_ref: str
    capability_snapshot_digest: str


class AgentTurnResult(BaseModel):
    status: Literal["complete", "partial", "failed", "cancelled"]
    message: str
    plan: AgentPlan
    result_blocks: list[AgentResultBlock] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    business_run_ids: list[str] = Field(default_factory=list)
    errors: list[ErrorEnvelope] = Field(default_factory=list)
    retryable_errors: list[ErrorEnvelope] = Field(default_factory=list)
    total_duration_ms: int = 0


class AgentTurnCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=100)
    model_id: str | None = None


class AgentTurnResume(BaseModel):
    answer: str | None = Field(default=None, max_length=2000)
    approved: bool | None = None

    @model_validator(mode="after")
    def require_one_resume_value(self) -> AgentTurnResume:
        if self.answer is None and self.approved is None:
            raise ValueError("AGENT_RESUME_PAYLOAD_REQUIRED")
        return self


class AgentTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    request_id: str
    client_message_id: str
    status: TurnStatus
    message: str
    workflow_version: str
    plan: dict[str, Any]
    result: dict[str, Any]
    error: dict[str, Any] | None
    total_duration_ms: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AgentTurnEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    turn_id: str
    sequence: int
    event_type: str
    elapsed_ms: int
    step_id: str | None
    data: dict[str, Any]
    created_at: datetime


class ContextTraceLayer(BaseModel):
    name: str
    version: str
    size_chars: int
    summary_hash: str
    content: None = None


class ContextSnapshot(BaseModel):
    base_prompt_version: str
    domain_ids: list[str]
    tool_ids: list[str]
    system_prompt: str
    trace_layers: list[ContextTraceLayer]
