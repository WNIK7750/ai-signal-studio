from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_signal_api.database import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentConversationModel(Base):
    __tablename__ = "agent_conversations"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("conversation")
    )
    title: Mapped[str] = mapped_column(
        String(160), default="Workspace Agent"
    )
    title_source: Mapped[str] = mapped_column(
        String(24), default="auto"
    )
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True
    )
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active_turn_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unread: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    messages: Mapped[list[AgentMessageModel]] = relationship(
        back_populates="conversation"
    )


class AgentMessageModel(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="uq_agent_message_client_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("message")
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(24), index=True)
    content: Mapped[str] = mapped_column(Text)
    client_message_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    turn_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    capability_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )
    result_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schedule_draft: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    task_draft: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, nullable=True
    )
    requested_model_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    effective_model_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    model_switched: Mapped[bool] = mapped_column(Boolean, default=False)
    error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    conversation: Mapped[AgentConversationModel] = relationship(
        back_populates="messages"
    )


class AgentTurnModel(Base):
    __tablename__ = "agent_turns"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id",
            "client_message_id",
            name="uq_agent_turn_client_message",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("turn")
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("agent_conversations.id"), index=True
    )
    request_id: Mapped[str] = mapped_column(
        String(80), unique=True, index=True
    )
    client_message_id: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(24), default="queued", index=True
    )
    message: Mapped[str] = mapped_column(Text)
    workflow_version: Mapped[str] = mapped_column(
        String(24), default="0.4.0"
    )
    manifest: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    last_event_sequence: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    checkpoint_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    lease_owner: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deadline_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentTurnStepModel(Base):
    __tablename__ = "agent_turn_steps"
    __table_args__ = (
        UniqueConstraint("turn_id", "step_id", name="uq_agent_turn_step"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("turnstep")
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    domain_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    capability_id: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AgentTurnEventModel(Base):
    __tablename__ = "agent_turn_events"
    __table_args__ = (
        UniqueConstraint(
            "turn_id",
            "sequence",
            name="uq_agent_turn_event_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("event")
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    step_id: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class AgentResultBlockModel(Base):
    __tablename__ = "agent_result_blocks"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id"), index=True
    )
    block_type: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(240))
    position: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SourceConfigModel(Base):
    __tablename__ = "source_configs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("src")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    health_status: Mapped[str] = mapped_column(
        String(24), default="unknown", index=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    last_items_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    raw_items: Mapped[list[RawItemModel]] = relationship(
        back_populates="source"
    )


class CollectionRunModel(Base):
    __tablename__ = "collection_runs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("run")
    )
    status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True
    )
    coverage_status: Mapped[str] = mapped_column(
        String(24), default="unknown", index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    task_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    trigger_type: Mapped[str] = mapped_column(
        String(24), default="manual", index=True
    )
    parent_run_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(160), nullable=True, index=True
    )
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_version_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    items_collected: Mapped[int] = mapped_column(Integer, default=0)
    items_added: Mapped[int] = mapped_column(Integer, default=0)
    funnel_counts: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    warning_codes: Mapped[list[str]] = mapped_column(JSON, default=list)
    errors: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class RawItemModel(Base):
    __tablename__ = "raw_items"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("raw")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_configs.id"), index=True
    )
    external_id: Mapped[str | None] = mapped_column(String(320), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    source: Mapped[SourceConfigModel] = relationship(
        back_populates="raw_items"
    )
    intelligence: Mapped[IntelligenceItemModel | None] = relationship(
        back_populates="raw_item",
        uselist=False,
        cascade="all, delete-orphan",
    )


class IntelligenceItemModel(Base):
    __tablename__ = "intelligence_items"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("info")
    )
    raw_item_id: Mapped[str] = mapped_column(
        ForeignKey("raw_items.id"), unique=True, index=True
    )
    summary: Mapped[str] = mapped_column(String(600))
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    priority: Mapped[str] = mapped_column(
        String(24), default="normal", index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )

    raw_item: Mapped[RawItemModel] = relationship(
        back_populates="intelligence"
    )


class CapabilityInvocationModel(Base):
    __tablename__ = "capability_invocations"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("inv")
    )
    capability_id: Mapped[str] = mapped_column(String(120), index=True)
    capability_version: Mapped[str] = mapped_column(
        String(24), default="1.0.0"
    )
    request_id: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[str] = mapped_column(String(40), index=True)
    actor_id: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="running")
    input_digest: Mapped[str] = mapped_column(String(64))
    output_digest: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CommonPlanModel(Base):
    __tablename__ = "common_plans"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("plan")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    prompt: Mapped[str] = mapped_column(Text)
    time_range_hours: Mapped[int] = mapped_column(Integer, default=24)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ScheduledTaskModel(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("task")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("common_plans.id"), index=True
    )
    frequency: Mapped[str] = mapped_column(String(32), default="daily")
    time_of_day: Mapped[str] = mapped_column(String(5), default="09:00")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CollectionTaskModel(Base):
    __tablename__ = "collection_tasks"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("task")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default="draft", index=True
    )
    latest_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    active_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    pinned: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CollectionTaskVersionModel(Base):
    __tablename__ = "collection_task_versions"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "version_number",
            name="uq_collection_task_version",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("taskver")
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("collection_tasks.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    change_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class TaskDraftModel(Base):
    __tablename__ = "task_drafts"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("taskdraft")
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_tasks.id"), nullable=True, index=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_conversations.id"), nullable=True, index=True
    )
    base_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    config: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(24), default="editing", index=True
    )
    confirmed_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceVersionModel(Base):
    __tablename__ = "source_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "config_hash",
            name="uq_source_version_hash",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("sourcever")
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_configs.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    adapter_type: Mapped[str] = mapped_column(String(40))
    adapter_version: Mapped[str] = mapped_column(String(24), default="1")
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class SourceRunResultModel(Base):
    __tablename__ = "source_run_results"
    __table_args__ = (
        UniqueConstraint("run_id", "source_id", name="uq_run_source_result"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("sourcerun")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("source_configs.id"), index=True
    )
    source_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_versions.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(24), default="running")
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaskRunItemModel(Base):
    __tablename__ = "task_run_items"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "intelligence_item_id",
            name="uq_task_run_item",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("runitem")
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("collection_runs.id"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("collection_tasks.id"), nullable=True, index=True
    )
    intelligence_item_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_items.id"), index=True
    )
    decision: Mapped[str] = mapped_column(String(24), default="included")
    reason_code: Mapped[str] = mapped_column(
        String(80), default="TASK_RULES_MATCHED"
    )
    matched_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    rank: Mapped[int] = mapped_column(Integer, default=0)


class WorkspaceItemStateModel(Base):
    __tablename__ = "workspace_item_states"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("itemstate")
    )
    intelligence_item_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_items.id"), unique=True, index=True
    )
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    starred: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SavedViewModel(Base):
    __tablename__ = "saved_views"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("view")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    query: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    display: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    pinned: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class ReviewBatchModel(Base):
    __tablename__ = "review_batches"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("review")
    )
    status: Mapped[str] = mapped_column(
        String(24), default="pending", index=True
    )
    item_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (
        UniqueConstraint("batch_id", "item_id", name="uq_review_item"),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("decision")
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("review_batches.id"), index=True
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_items.id"), index=True
    )
    decision: Mapped[str] = mapped_column(String(24), index=True)
    edited_title: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    edited_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    actor_type: Mapped[str] = mapped_column(String(40), default="user")
    actor_id: Mapped[str] = mapped_column(String(80), default="local")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class CardModel(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("card")
    )
    intelligence_item_id: Mapped[str] = mapped_column(
        ForeignKey("intelligence_items.id"), unique=True, index=True
    )
    review_decision_id: Mapped[str] = mapped_column(
        ForeignKey("review_decisions.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(500))
    summary: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    cover_variant: Mapped[int] = mapped_column(Integer, default=0)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(160))
    source_kind: Mapped[str] = mapped_column(String(40), index=True)
    canonical_url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    priority: Mapped[str] = mapped_column(
        String(24), default="normal", index=True
    )
    topics: Mapped[list[str]] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    template_id: Mapped[str] = mapped_column(
        String(40), default="offline-quote"
    )
    cover_source: Mapped[str] = mapped_column(
        String(24), default="offline"
    )
    render_status: Mapped[str] = mapped_column(
        String(24), default="not_rendered", index=True
    )
    rendered_artifact_id: Mapped[str | None] = mapped_column(
        ForeignKey("artifacts.id"), nullable=True
    )
    rendered_revision: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class AgentPackVersionModel(Base):
    __tablename__ = "agent_pack_versions"
    __table_args__ = (
        UniqueConstraint(
            "pack_id",
            "version",
            "content_digest",
            name="uq_agent_pack_version_digest",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("packversion")
    )
    pack_id: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40))
    content_digest: Mapped[str] = mapped_column(String(64), index=True)
    storage_uri: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(24), default="inactive", index=True
    )
    previous_version_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    validation_result: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict
    )
    imported_by: Mapped[str] = mapped_column(String(80), default="local")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("artifact")
    )
    workspace_id: Mapped[str] = mapped_column(
        String(80), default="local", index=True
    )
    media_type: Mapped[str] = mapped_column(String(160))
    filename: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True
    )
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TranscriptionSessionModel(Base):
    __tablename__ = "transcription_sessions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("stt")
    )
    workspace_id: Mapped[str] = mapped_column(
        String(80), default="local", index=True
    )
    provider: Mapped[str] = mapped_column(String(80), default="fake")
    status: Mapped[str] = mapped_column(
        String(24), default="created", index=True
    )
    language: Mapped[str] = mapped_column(String(24), default="zh")
    audio_format: Mapped[str] = mapped_column(
        String(24), default="webm_opus"
    )
    sample_rate: Mapped[int] = mapped_column(Integer, default=48000)
    token_digest: Mapped[str] = mapped_column(String(64))
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    final_text: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
