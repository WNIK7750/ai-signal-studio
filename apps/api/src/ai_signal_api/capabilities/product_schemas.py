from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_signal_api.schemas import (
    AgentTaskDraft,
    AgentConversationPatch,
    AgentConversationSummary,
    CardRead,
    CollectionRunRead,
    ModelConfigRead,
    ScheduleDraft,
    SourcePatch,
    SourceRead,
    TaskPatch,
    TaskRead,
    WorkspaceItemStatePatch,
)


class EmptyInput(BaseModel):
    pass


class SourceListResult(BaseModel):
    items: list[SourceRead]


class SourceTestInput(BaseModel):
    source_id: str


class SourcePatchCapabilityInput(SourcePatch):
    source_id: str


class TaskListResult(BaseModel):
    items: list[TaskRead]


class TaskGetInput(BaseModel):
    task_id: str


class TaskPatchCapabilityInput(TaskPatch):
    task_id: str


class TaskDraftProposalInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class TaskDraftProposalResult(BaseModel):
    status: Literal["pending_confirmation"] = "pending_confirmation"
    schedule_draft: ScheduleDraft
    task_draft: AgentTaskDraft


class RunListInput(BaseModel):
    limit: int = Field(default=30, ge=1, le=100)


class RunListResult(BaseModel):
    items: list[CollectionRunRead]


class RunGetInput(BaseModel):
    run_id: str


class CardQueryInput(BaseModel):
    day: date | None = None
    month: str | None = Field(
        default=None,
        pattern=r"^\d{4}-(?:0[1-9]|1[0-2])$",
    )
    priority: str | None = None
    source_kind: str | None = None
    topic: str | None = None


class CardGetInput(BaseModel):
    card_id: str


class ModelListResult(BaseModel):
    items: list[ModelConfigRead]


class ModelSelectionInput(BaseModel):
    model_id: str


class InformationStateCapabilityInput(WorkspaceItemStatePatch):
    item_id: str


class ConversationListInput(BaseModel):
    scope: Literal["active", "archived", "deleted"] = "active"
    search: str | None = Field(default=None, max_length=160)


class ConversationListResult(BaseModel):
    items: list[AgentConversationSummary]


class ConversationPatchCapabilityInput(AgentConversationPatch):
    conversation_id: str


class ConversationIdInput(BaseModel):
    conversation_id: str


class AppearanceActionInput(BaseModel):
    theme: Literal["system", "light", "dark", "high-contrast"]


class ClientActionResult(BaseModel):
    action: Literal[
        "select_model",
        "set_appearance",
        "open_model_settings",
    ]
    payload: dict[str, Any]
