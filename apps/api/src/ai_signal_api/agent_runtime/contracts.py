from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WORKFLOW_VERSION = "0.7.0"


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

CapabilityId = Literal[
    "collection.run.start",
    "web.search.collect",
    "intelligence.timeline.query",
    "intelligence.search",
    "intelligence.recommend",
    "research.filter",
    "research.recommend",
    "research.match_requirements",
    "research.compare",
    "research.trend_brief",
    "research.coverage_gap",
    "agent_pack.search",
    "artifact.search",
    "poster.card.update",
    "poster.card.render",
    "poster.draft.generate",
    "review.batch.submit",
    "task.run.start",
    "task.draft.propose",
    "source.list",
    "source.test",
    "source.update",
    "task.list",
    "task.get",
    "task.update",
    "run.list",
    "run.get",
    "card.list",
    "card.get",
    "information.state.update",
    "model.list",
    "model.select",
    "conversation.list",
    "conversation.update",
    "conversation.archive",
    "conversation.restore",
    "appearance.set",
    "agent.message.complete",
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
        "result_summary",
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
        "model_response",
    ]
    title: str
    data: dict[str, Any]


class ModelReasoningOutput(BaseModel):
    status: Literal["completed"] = "completed"
    content: str = Field(min_length=1, max_length=8000)
    basis: Literal[
        "conversation_context",
        "tool_evidence",
        "mixed",
    ]
    evidence_boundary: str = Field(min_length=1, max_length=1000)
    information_ids: list[str] = Field(default_factory=list, max_length=20)
    effective_model_id: str = Field(min_length=1, max_length=200)


class AcceptancePolicy(BaseModel):
    id: Literal[
        "information_results.v1",
        "capability_effect.v1",
        "artifact_created.v1",
        "synthesis_grounded.v1",
        "contextual_response.v1",
    ]
    params: dict[str, Any] = Field(default_factory=dict)


class PlanStep(BaseModel):
    step_id: str
    title: str
    goal: str
    kind: Literal[
        "capability",
        "domain_agent",
        "domain_workflow",
        "model_reasoning",
    ]
    domains: list[str] = Field(default_factory=list, max_length=3)
    capability_id: CapabilityId | None = Field(
        default=None,
        description=(
            "Exact registered capability ID from this enum; never invent, "
            "translate, abbreviate, or prefix an ID. It may be omitted only "
            "for a model_reasoning step."
        )
    )
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
    satisfies: list[str] = Field(
        default_factory=list,
        max_length=6,
        description=(
            "Canonical goal deliverables completed by this step. Research "
            "uses recommendations, trend_summary, and evidence."
        ),
    )

    @model_validator(mode="after")
    def validate_execution_mode(self) -> PlanStep:
        if self.kind == "model_reasoning":
            if self.capability_id is not None:
                raise ValueError("AGENT_PLAN_MODEL_REASONING_HAS_CAPABILITY")
            if self.side_effect != "read":
                raise ValueError("AGENT_PLAN_MODEL_REASONING_MUST_BE_READ")
            if self.acceptance_policy.id != "contextual_response.v1":
                raise ValueError(
                    "AGENT_PLAN_MODEL_REASONING_ACCEPTANCE_INVALID"
                )
            return self
        if not self.domains:
            raise ValueError("AGENT_PLAN_DOMAIN_REQUIRED")
        if self.capability_id is None:
            raise ValueError("AGENT_PLAN_CAPABILITY_REQUIRED")
        return self


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


class GoalTimeWindow(BaseModel):
    lookback_hours: int = Field(ge=1, le=24 * 365)
    published_from: datetime | None = None
    published_to: datetime | None = None


class AgentGoalSpec(BaseModel):
    operation_mode: Literal[
        "direct",
        "collect_then_analyze",
        "analyze_existing",
        "execute",
    ]
    topic: str = Field(default="AI", min_length=1, max_length=120)
    time_window: GoalTimeWindow
    max_items: int = Field(
        ge=1,
        le=20,
        description="Exact requested result count; Chinese 三个 means 3.",
    )
    ranking_criterion: Literal["impact", "relevance", "recency"]
    deliverables: list[str] = Field(
        min_length=1,
        max_length=8,
        description=(
            "Canonical deliverable IDs. Complex research must use exactly "
            "recommendations, trend_summary, and evidence."
        ),
    )
    use_existing: bool = True
    requires_collection: bool = False
    requires_synthesis: bool = False


class AgentPlanningOutput(BaseModel):
    goal: AgentGoalSpec
    plan: AgentPlan


def validate_goal_plan_coverage(
    goal: AgentGoalSpec,
    plan: AgentPlan,
) -> list[str]:
    """Return stable, model-actionable gaps between a goal and its plan."""

    gaps: list[str] = []
    capabilities = [step.capability_id for step in plan.steps]
    required: list[str] = []
    if goal.operation_mode in {
        "collect_then_analyze",
        "analyze_existing",
    }:
        required.append("intelligence.search")
        if goal.requires_collection:
            required.insert(0, "collection.run.start")
            required.insert(2, "web.search.collect")
        if "recommendations" in goal.deliverables:
            required.append("research.recommend")
        if goal.requires_synthesis or "trend_summary" in goal.deliverables:
            required.append("research.trend_brief")
    for capability_id in required:
        if capability_id not in capabilities:
            gaps.append(f"missing_capability:{capability_id}")
    capability_steps = {
        step.capability_id: step
        for step in plan.steps
    }
    for dependency_id, capability_id in zip(required, required[1:]):
        dependency = capability_steps.get(dependency_id)
        step = capability_steps.get(capability_id)
        if (
            dependency is not None
            and step is not None
            and dependency.step_id not in step.dependencies
        ):
            gaps.append(
                f"missing_dependency:{capability_id}:{dependency_id}"
            )

    covered = {
        deliverable
        for step in plan.steps
        for deliverable in step.satisfies
    }
    for deliverable in goal.deliverables:
        if deliverable not in covered:
            gaps.append(f"uncovered_deliverable:{deliverable}")

    constraints = plan.constraints
    if goal.operation_mode in {
        "collect_then_analyze",
        "analyze_existing",
    }:
        if int(constraints.get("lookback_hours", 0)) != (
            goal.time_window.lookback_hours
        ):
            gaps.append("constraint_mismatch:lookback_hours")
        if int(constraints.get("max_items", 0)) != goal.max_items:
            gaps.append("constraint_mismatch:max_items")
        if constraints.get("ranking_criterion") != goal.ranking_criterion:
            gaps.append("constraint_mismatch:ranking_criterion")

    for step in plan.steps:
        if step.capability_id not in {
            "intelligence.search",
            "web.search.collect",
            "research.recommend",
            "research.trend_brief",
        }:
            continue
        arguments = step.arguments
        if arguments and int(
            arguments.get(
                "lookback_hours",
                goal.time_window.lookback_hours,
            )
        ) != goal.time_window.lookback_hours:
            gaps.append(f"argument_mismatch:{step.step_id}:lookback_hours")
        if step.capability_id in {
            "research.recommend",
            "research.trend_brief",
        }:
            if int(arguments.get("limit", 0)) != goal.max_items:
                gaps.append(f"argument_mismatch:{step.step_id}:limit")
            if arguments.get("rank_by") != goal.ranking_criterion:
                gaps.append(f"argument_mismatch:{step.step_id}:rank_by")
    return list(dict.fromkeys(gaps))


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
    workflow_version: str = WORKFLOW_VERSION
    state_schema_version: str = "1.2.0"
    plan_schema_version: str = "1.2.0"
    event_schema_version: str = "1.2.0"
    base_prompt_version: str = "base-prompt@1.0.0"
    domain_pack_versions: dict[str, str] = Field(default_factory=dict)
    tool_catalog_version: str = "1"
    requested_model_id: str | None = None
    effective_model_id: str | None = None
    model_config_ref: str
    capability_snapshot_digest: str
    artifact_ids: list[str] = Field(default_factory=list, max_length=20)


class AgentTurnResult(BaseModel):
    status: Literal["complete", "partial", "failed", "cancelled"]
    message: str
    goal: AgentGoalSpec | None = None
    plan: AgentPlan
    result_blocks: list[AgentResultBlock] = Field(default_factory=list)
    capability_results: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    business_run_ids: list[str] = Field(default_factory=list)
    errors: list[ErrorEnvelope] = Field(default_factory=list)
    retryable_errors: list[ErrorEnvelope] = Field(default_factory=list)
    total_duration_ms: int = 0


class AgentTurnCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    client_message_id: str = Field(min_length=1, max_length=100)
    model_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list, max_length=20)


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
    requested_model_id: str | None = None
    effective_model_id: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    plan: dict[str, Any]
    result: dict[str, Any]
    error: dict[str, Any] | None
    total_duration_ms: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @model_validator(mode="after")
    def project_model_ids(self) -> AgentTurnRead:
        self.requested_model_id = self.requested_model_id or self.manifest.get(
            "requested_model_id"
        )
        self.effective_model_id = self.effective_model_id or self.manifest.get(
            "effective_model_id"
        )
        return self


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
