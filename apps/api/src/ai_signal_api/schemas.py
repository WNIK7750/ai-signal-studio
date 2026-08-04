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


SourceKind = Literal["demo", "rss", "github_releases"]
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
        return self


class SourcePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: SourceKind
    config: dict[str, Any]
    enabled: bool
    created_at: datetime
    updated_at: datetime


class CollectionRunStart(BaseModel):
    source_ids: list[str] = Field(default_factory=list)


class CollectionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: Literal["pending", "running", "completed", "partial", "failed"]
    source_ids: list[str]
    items_collected: int
    items_added: int
    errors: list[dict[str, Any]]
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class TimelineQuery(BaseModel):
    search: str | None = None
    priority: Priority | None = None
    source_kind: SourceKind | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


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


class TimelinePage(BaseModel):
    total: int
    items: list[TimelineItem]


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


class AgentRunResponse(BaseModel):
    message: str
    capability_calls: list[AgentCapabilityCall]
    result: dict[str, Any]
    schedule_draft: ScheduleDraft | None = None
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
    role: Literal["assistant", "user"]
    content: str
    capability_calls: list[AgentCapabilityCall]
    error_code: str | None
    effective_model_id: str | None
    image_count: int
    created_at: datetime


class AgentConversationRead(BaseModel):
    id: str
    title: str
    status: Literal["active", "archived"]
    messages: list[AgentMessageRead]
    created_at: datetime
    updated_at: datetime


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


class CardPage(BaseModel):
    total: int
    items: list[CardRead]
