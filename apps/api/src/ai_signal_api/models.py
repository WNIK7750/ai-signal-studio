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
    status: Mapped[str] = mapped_column(
        String(24), default="active", index=True
    )
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
    capability_calls: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )
    result_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    schedule_draft: Mapped[dict[str, Any] | None] = mapped_column(
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


class SourceConfigModel(Base):
    __tablename__ = "source_configs"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("src")
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
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
    source_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    items_collected: Mapped[int] = mapped_column(Integer, default=0)
    items_added: Mapped[int] = mapped_column(Integer, default=0)
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
