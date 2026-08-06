from __future__ import annotations

import base64
import binascii
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


SourceKind = Literal["demo", "rss", "github_releases", "web_search"]
Priority = Literal["important", "watch", "normal"]


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: SourceKind
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_kind_config(self) -> SourceCreate:
        if self.kind == "rss" and not str(
            self.config.get("url", "")
        ).strip():
            raise ValueError("SOURCE_CONFIG_URL_REQUIRED")
        if self.kind == "github_releases" and not str(
            self.config.get("repository", "")
        ).strip():
            raise ValueError("SOURCE_CONFIG_REPOSITORY_REQUIRED")
        if self.kind == "web_search" and not str(
            self.config.get("origin", "")
        ).strip():
            raise ValueError("SOURCE_CONFIG_ORIGIN_REQUIRED")
        return self


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    config: dict[str, Any] | None = None
    enabled: bool | None = None

    @field_validator("name")
    @classmethod
    def reject_null_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("SOURCE_NAME_REQUIRED")
        return value

    @field_validator("config")
    @classmethod
    def reject_null_config(
        cls,
        value: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if value is None:
            raise ValueError("SOURCE_CONFIG_REQUIRED")
        return value

    @field_validator("enabled")
    @classmethod
    def reject_null_enabled(cls, value: bool | None) -> bool:
        if value is None:
            raise ValueError("SOURCE_ENABLED_REQUIRED")
        return value


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: SourceKind
    config: dict[str, Any]
    enabled: bool
    health_status: Literal["unknown", "healthy", "warning", "error"]
    last_success_at: datetime | None
    last_error_at: datetime | None
    last_error_code: str | None
    last_items_count: int
    created_at: datetime
    updated_at: datetime


class SourceTestRead(BaseModel):
    source_id: str | None
    status: Literal["healthy", "error"]
    items_count: int
    sample_titles: list[str] = Field(default_factory=list)
    error_code: str | None = None


class CollectionRunStart(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    task_id: str | None = None
    task_version_id: str | None = None
    trigger_type: Literal["manual", "schedule", "agent", "test", "retry"] = (
        "manual"
    )


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: Literal["pending", "running", "completed", "partial", "failed"]
    execution_status: Literal[
        "pending",
        "running",
        "completed",
        "partial",
        "failed",
        "cancelled",
        "skipped",
    ] = Field(validation_alias="status")
    coverage_status: Literal["unknown", "met", "insufficient"]
    task_id: str | None
    task_version_id: str | None
    trigger_type: str
    parent_run_id: str | None
    source_ids: list[str]
    source_version_ids: list[str]
    items_collected: int
    items_added: int
    funnel_counts: dict[str, int]
    warning_codes: list[str]
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TimelineQuery(BaseModel):
    search: str | None = None
    priority: Priority | None = None
    source_kind: SourceKind | None = None
    source_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    task_id: str | None = None
    starred: bool | None = None
    seen: bool | None = None
    archived: bool | None = None
    published_from: datetime | None = None
    published_to: datetime | None = None
    sort: Literal["newest", "oldest"] = "newest"
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    cursor: str | None = None


class TimelineItem(BaseModel):
    id: str
    title: str
    summary: str
    canonical_url: str
    source_id: str
    source_name: str
    source_kind: SourceKind
    published_at: datetime
    topics: list[str]
    priority: Priority
    task_ids: list[str] = Field(default_factory=list)
    seen: bool = False
    starred: bool = False
    archived: bool = False
    note: str = ""


class TimelinePage(BaseModel):
    total: int
    items: list[TimelineItem]
    next_cursor: str | None = None
    has_more: bool = False


class ExecutionContext(BaseModel):
    request_id: str
    actor_id: str = "local"
    actor_type: Literal[
        "user",
        "internal_agent",
        "system",
        "external_agent",
    ] = "user"
    idempotency_key: str | None = None


class CapabilityInvocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    capability_id: str
    capability_version: str
    request_id: str
    actor_type: str
    actor_id: str
    status: str
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None


class AgentRunRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)
    client_message_id: str | None = Field(default=None, max_length=100)
    model_id: str | None = None
    image_urls: list[str] = Field(default_factory=list, max_length=4)
    artifact_ids: list[str] = Field(default_factory=list, max_length=4)

    @field_validator("image_urls")
    @classmethod
    def validate_images(cls, values: list[str]) -> list[str]:
        allowed_headers = {
            "data:image/png;base64",
            "data:image/jpeg;base64",
            "data:image/webp;base64",
        }
        for value in values:
            if value.startswith("https://"):
                continue
            header, separator, encoded = value.partition(",")
            if separator != "," or header not in allowed_headers:
                raise ValueError("IMAGE_TYPE_UNSUPPORTED")
            try:
                decoded = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as error:
                raise ValueError("IMAGE_DATA_INVALID") from error
            if len(decoded) > 5 * 1024 * 1024:
                raise ValueError("IMAGE_TOO_LARGE")
        return values


class AgentCapabilityCall(BaseModel):
    capability_id: str
    status: str


class ScheduleDraft(BaseModel):
    frequency: Literal["daily"]
    time_of_day: str
    plan_name: str


class AgentTaskDraft(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1, max_length=500)
    status: Literal["draft", "enabled"] = "draft"
    pinned: bool = True
    config: dict[str, Any]


class AgentRunResponse(BaseModel):
    message: str
    capability_calls: list[AgentCapabilityCall]
    result: dict[str, Any]
    schedule_draft: ScheduleDraft | None = None
    task_draft: AgentTaskDraft | None = None
    requested_model_id: str | None = None
    effective_model_id: str | None = None
    model_switched: bool = False
    conversation_id: str | None = None
    user_message_id: str | None = None
    assistant_message_id: str | None = None


class AgentMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    turn_id: str | None
    role: Literal["assistant", "user"]
    content: str
    result: dict[str, Any] = Field(validation_alias="result_data")
    capability_calls: list[AgentCapabilityCall]
    schedule_draft: ScheduleDraft | None
    task_draft: AgentTaskDraft | None
    error_code: str | None
    effective_model_id: str | None
    image_count: int
    created_at: datetime


class AgentConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)


class AgentConversationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None


class AgentConversationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    title_source: Literal["auto", "manual"]
    status: Literal["active", "archived"]
    pinned_at: datetime | None
    archived_at: datetime | None
    deleted_at: datetime | None
    active_turn_id: str | None
    last_message_at: datetime | None
    unread: bool
    created_at: datetime
    updated_at: datetime


class AgentConversationRead(AgentConversationSummary):
    messages: list[AgentMessageRead]


ModelProvider = Literal["heuristic", "openai_compatible"]


class ModelConfigCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    provider_id: str | None = Field(default=None, max_length=160)
    provider_name: str | None = Field(default=None, max_length=160)
    model_id: str = Field(min_length=1, max_length=200)
    base_url: str = Field(default="", max_length=1000)
    api_key: SecretStr | None = None
    supports_vision: bool = False
    output_token_limit: int | None = Field(
        default=None,
        ge=256,
        le=1_000_000,
    )
    enabled: bool = True
    is_default: bool = False


class ModelConfigPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    provider_id: str | None = Field(default=None, max_length=160)
    provider_name: str | None = Field(default=None, max_length=160)
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = Field(default=None, max_length=1000)
    api_key: SecretStr | None = None
    supports_vision: bool | None = None
    output_token_limit: int | None = Field(
        default=None,
        ge=256,
        le=1_000_000,
    )
    is_default: bool | None = None


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    provider: ModelProvider
    provider_id: str
    provider_name: str
    model_id: str
    base_url: str
    has_api_key: bool
    supports_vision: bool
    output_token_limit: int | None
    enabled: bool
    is_default: bool
    connection_status: Literal[
        "pending",
        "healthy",
        "needs_retest",
        "error",
        "not_applicable",
    ]
    connection_checked_at: datetime | None
    connection_error_code: str | None
    created_at: datetime
    updated_at: datetime


class ProviderConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    base_url: str
    protocol: ModelProvider
    has_api_key: bool


class ModelConnectionRead(BaseModel):
    status: Literal["ok"]
    message: str


class CommonPlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=4000)
    time_range_hours: int = Field(default=24, ge=1, le=720)
    topics: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class CommonPlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    prompt: str | None = Field(default=None, min_length=1, max_length=4000)
    time_range_hours: int | None = Field(default=None, ge=1, le=720)
    topics: list[str] | None = None
    source_ids: list[str] | None = None


class CommonPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    prompt: str
    time_range_hours: int
    topics: list[str]
    source_ids: list[str]
    created_at: datetime
    updated_at: datetime


class ScheduledTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    plan_id: str
    frequency: Literal["daily"] = "daily"
    time_of_day: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    enabled: bool = True


class ScheduledTaskPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    plan_id: str | None = None
    frequency: Literal["daily"] | None = None
    time_of_day: str | None = Field(
        default=None,
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    enabled: bool | None = None


class ScheduledTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plan_id: str
    frequency: str
    time_of_day: str
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


TaskStatus = Literal["draft", "enabled", "paused", "archived"]
TaskScheduleMode = Literal[
    "manual",
    "interval",
    "daily",
    "weekdays",
    "weekly",
]


class TaskSourceSelection(BaseModel):
    mode: Literal["selected", "all_enabled"] = "selected"
    include_ids: list[str] = Field(default_factory=list)
    exclude_ids: list[str] = Field(default_factory=list)
    required_ids: list[str] = Field(default_factory=list)
    fallback_ids: list[str] = Field(default_factory=list)
    per_source_max_items: int = Field(default=20, ge=1, le=100)


class TaskMatching(BaseModel):
    topics: list[str] = Field(default_factory=list)
    include_any: list[str] = Field(default_factory=list)
    include_all: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)
    search_scope: Literal["title", "title_and_content"] = "title_and_content"
    languages: list[str] = Field(default_factory=lambda: ["zh", "en"])


class TaskTimeWindow(BaseModel):
    mode: Literal["rolling", "since_last_success"] = "rolling"
    lookback_hours: int = Field(default=24, ge=1, le=720)
    overlap_hours: int = Field(default=2, ge=0, le=24)
    timezone: str = "Asia/Shanghai"


class TaskQuantity(BaseModel):
    min_items: int = Field(default=5, ge=0, le=500)
    target_items: int = Field(default=10, ge=0, le=500)
    max_items: int = Field(default=30, ge=1, le=500)

    @model_validator(mode="after")
    def validate_range(self) -> TaskQuantity:
        if not self.min_items <= self.target_items <= self.max_items:
            raise ValueError("TASK_ITEMS_RANGE_INVALID")
        return self


class TaskImportance(BaseModel):
    accepted_levels: list[Priority] = Field(
        default_factory=lambda: ["important", "watch", "normal"]
    )


class TaskQualityRequirements(BaseModel):
    require_source_link: bool = True
    prefer_primary_source: bool = True
    allow_unknown_publish_time: bool = False
    require_extractable_content: bool = True


class TaskDeduplication(BaseModel):
    mode: Literal["conservative", "balanced", "event"] = "balanced"
    window_days: int = Field(default=31, ge=1, le=365)
    across_runs: bool = True
    preserve_related_sources: bool = True


class TaskSchedule(BaseModel):
    mode: TaskScheduleMode = "manual"
    time_of_day: str = Field(
        default="09:00",
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
    )
    weekdays: list[int] = Field(default_factory=list)
    interval_hours: int | None = Field(default=None, ge=1, le=720)


class TaskDelivery(BaseModel):
    destination: Literal["task_view", "timeline", "review"] = "task_view"
    notify_when: Literal[
        "always",
        "important_or_problem",
        "problem_only",
        "never",
    ] = "important_or_problem"
    summary_max_chars: int = Field(default=400, ge=100, le=1000)


class TaskConfig(BaseModel):
    sources: TaskSourceSelection = Field(default_factory=TaskSourceSelection)
    matching: TaskMatching = Field(default_factory=TaskMatching)
    time_window: TaskTimeWindow = Field(default_factory=TaskTimeWindow)
    quantity: TaskQuantity = Field(default_factory=TaskQuantity)
    importance: TaskImportance = Field(default_factory=TaskImportance)
    quality_requirements: TaskQualityRequirements = Field(
        default_factory=TaskQualityRequirements
    )
    deduplication: TaskDeduplication = Field(
        default_factory=TaskDeduplication
    )
    schedule: TaskSchedule = Field(default_factory=TaskSchedule)
    delivery: TaskDelivery = Field(default_factory=TaskDelivery)


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1, max_length=500)
    status: TaskStatus = "draft"
    pinned: bool = True
    config: TaskConfig


class TaskPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    goal: str | None = Field(default=None, min_length=1, max_length=500)
    status: TaskStatus | None = None
    pinned: bool | None = None
    config: TaskConfig | None = None
    change_note: str = Field(default="", max_length=500)


class TaskRead(BaseModel):
    id: str
    name: str
    goal: str
    status: TaskStatus
    latest_version_id: str | None
    active_version_id: str | None
    pinned: bool
    version_number: int | None
    config: TaskConfig | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TaskPreviewSample(BaseModel):
    title: str
    source_name: str
    published_at: datetime
    priority: Priority
    reason: str


class TaskPreviewResult(BaseModel):
    funnel_counts: dict[str, int]
    samples: list[TaskPreviewSample]
    warning_codes: list[str] = Field(default_factory=list)


class TaskPreviewInput(BaseModel):
    config: TaskConfig | None = None


class TaskRunStart(BaseModel):
    task_version_id: str | None = None
    trigger_type: Literal["manual", "schedule", "agent", "retry"] = "manual"


class TaskRunRetry(BaseModel):
    mode: Literal["original_version", "current_version"] = "original_version"


class TaskRunCapabilityInput(TaskRunStart):
    task_id: str


class SourceRunResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    source_id: str
    source_version_id: str | None
    status: str
    fetched_count: int
    matched_count: int
    duplicate_count: int
    selected_count: int
    attempts: int
    error_code: str | None
    error_message: str | None


class TaskRunRead(CollectionRunRead):
    source_results: list[SourceRunResultRead] = Field(default_factory=list)


class WorkspaceItemStatePatch(BaseModel):
    seen: bool | None = None
    starred: bool | None = None
    archived: bool | None = None
    snoozed_until: datetime | None = None
    note: str | None = Field(default=None, max_length=2000)


class WorkspaceItemStateRead(BaseModel):
    intelligence_item_id: str
    seen: bool
    starred: bool
    archived: bool
    snoozed_until: datetime | None
    note: str


class SavedViewCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    query: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, Any] = Field(default_factory=dict)
    pinned: bool = True
    is_default: bool = False


class SavedViewPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    query: dict[str, Any] | None = None
    display: dict[str, Any] | None = None
    pinned: bool | None = None
    is_default: bool | None = None


class SavedViewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    query: dict[str, Any]
    display: dict[str, Any]
    pinned: bool
    is_default: bool
    created_at: datetime
    updated_at: datetime


ReviewDecision = Literal["keep", "reject", "defer"]


class ReviewDecisionInput(BaseModel):
    item_id: str
    decision: ReviewDecision
    edited_title: str | None = Field(default=None, max_length=500)
    edited_summary: str | None = Field(default=None, max_length=2000)
    note: str = Field(default="", max_length=1000)


class ReviewSubmitInput(BaseModel):
    batch_id: str | None = None
    decisions: list[ReviewDecisionInput] = Field(default_factory=list)
    default_decision: ReviewDecision | None = None
    confirm: bool = False


class ReviewItemRead(BaseModel):
    id: str
    title: str
    summary: str
    canonical_url: str
    source_name: str
    source_kind: SourceKind
    published_at: datetime
    topics: list[str]
    priority: Priority
    decision: ReviewDecision | None = None
    edited_title: str | None = None
    edited_summary: str | None = None
    note: str = ""


class ReviewBatchRead(BaseModel):
    id: str
    status: Literal["pending", "completed"]
    items: list[ReviewItemRead]
    created_at: datetime
    completed_at: datetime | None = None


class CardGenerateInput(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    max_chars: int = Field(default=400, ge=100, le=1000)


class CardGenerateResult(BaseModel):
    created: int
    existing: int
    card_ids: list[str]


class CardRead(BaseModel):
    id: str
    title: str
    summary: str
    key_points: list[str]
    cover_variant: int = Field(ge=0, le=5)
    cover_url: str | None = None
    source_name: str
    source_kind: SourceKind
    canonical_url: str
    published_at: datetime
    priority: Priority
    topics: list[str]
    revision: int = 1
    template_id: str = "offline-quote"
    cover_source: Literal["original", "offline"] = "offline"
    render_status: Literal[
        "not_rendered", "rendering", "rendered", "failed"
    ] = "not_rendered"
    rendered_artifact_id: str | None = None


class CardUpdateInput(BaseModel):
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=100, max_length=1000)
    key_points: list[str] = Field(min_length=1, max_length=6)
    template_id: Literal[
        "offline-quote",
        "offline-grid",
        "source-cover",
    ] = "offline-quote"
    cover_source: Literal["original", "offline"] = "offline"


class CardUpdateCapabilityInput(CardUpdateInput):
    card_id: str = Field(min_length=1, max_length=160)


class CardRenderCapabilityInput(BaseModel):
    card_id: str = Field(min_length=1, max_length=160)


class CardRenderResult(BaseModel):
    card_id: str
    artifact_id: str
    status: Literal["rendered", "failed"]
    width: int = 1200
    height: int = 1500


class CardPage(BaseModel):
    total: int
    items: list[CardRead]
