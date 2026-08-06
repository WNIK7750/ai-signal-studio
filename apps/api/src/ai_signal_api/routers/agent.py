from typing import Literal

import asyncio
import json

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Request,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.agent_runtime.service import WorkspaceAgentService
from ai_signal_api.agent_runtime.contracts import (
    AgentTurnCreate,
    AgentTurnRead,
    AgentTurnResume,
    AgentTurnResult,
)
from ai_signal_api.agent_runtime.harness import (
    AgentTurnService,
    TERMINAL_STATUSES,
    process_turn,
)
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.models import (
    AgentTurnEventModel,
    AgentTurnModel,
    CapabilityInvocationModel,
)
from ai_signal_api.modules.agent.conversation_service import (
    AgentConversationService,
    AgentTurnInProgressError,
)
from ai_signal_api.modules.agent_assets.artifacts import ArtifactService
from ai_signal_api.schemas import (
    AgentConversationCreate,
    AgentConversationPatch,
    AgentConversationRead,
    AgentConversationSummary,
    AgentRunRequest,
    AgentRunResponse,
    CapabilityInvocationRead,
)


router = APIRouter(prefix="/api", tags=["agent"])


@router.post(
    "/agent-conversations/{conversation_id}/turns",
    response_model=AgentTurnRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_agent_turn(
    conversation_id: str,
    payload: AgentTurnCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentTurnRead:
    executor = build_capability_executor(
        session,
        request.app.state.settings,
    )
    try:
        turn, created = AgentTurnService(session).create(
            conversation_id,
            payload,
            capability_ids=executor.registry.ids(),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if created:
        background_tasks.add_task(
            process_turn,
            request.app.state.session_factory,
            request.app.state.settings,
            request.app.state.model_configuration,
            request.app.state.agent_checkpointer,
            turn.id,
            payload.model_id,
        )
    return turn


@router.get(
    "/agent-turns/{turn_id}",
    response_model=AgentTurnRead,
)
def get_agent_turn(
    turn_id: str,
    session: Session = Depends(get_session),
) -> AgentTurnRead:
    try:
        return AgentTurnService(session).read(turn_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/agent-turns/{turn_id}/events")
def stream_agent_turn_events(
    turn_id: str,
    request: Request,
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
    ),
) -> StreamingResponse:
    try:
        sequence = max(0, int(last_event_id or 0))
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail="AGENT_EVENT_ID_INVALID",
        ) from error

    async def event_stream():
        nonlocal sequence
        while True:
            with request.app.state.session_factory() as event_session:
                turn = event_session.get(AgentTurnModel, turn_id)
                if turn is None:
                    yield (
                        "event: error\n"
                        'data: {"code":"AGENT_TURN_NOT_FOUND"}\n\n'
                    )
                    return
                events = list(
                    event_session.scalars(
                        select(AgentTurnEventModel)
                        .where(
                            AgentTurnEventModel.turn_id == turn_id,
                            AgentTurnEventModel.sequence > sequence,
                        )
                        .order_by(AgentTurnEventModel.sequence)
                    )
                )
                terminal = turn.status in TERMINAL_STATUSES
                for event in events:
                    sequence = event.sequence
                    payload = {
                        **event.data,
                        "elapsed_ms": event.elapsed_ms,
                        "step_id": event.step_id,
                    }
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        "data: "
                        f"{json.dumps(payload, ensure_ascii=False)}\n\n"
                    )
                if terminal and sequence >= turn.last_event_sequence:
                    return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/agent-turns/{turn_id}/cancel",
    response_model=AgentTurnRead,
)
def cancel_agent_turn(
    turn_id: str,
    session: Session = Depends(get_session),
) -> AgentTurnRead:
    try:
        return AgentTurnService(session).cancel(turn_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/agent-turns/{turn_id}/resume",
    response_model=AgentTurnRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def resume_agent_turn(
    turn_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    payload: AgentTurnResume | None = None,
    session: Session = Depends(get_session),
) -> AgentTurnRead:
    try:
        turn = AgentTurnService(session).read(turn_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    model = session.get(AgentTurnModel, turn_id)
    model_id = model.manifest.get("model_config_ref")
    if model_id == "workspace-default":
        model_id = None
    if turn.status in {
        "failed",
        "cancelled",
        "partial",
        "waiting_input",
        "waiting_approval",
    }:
        manifest = dict(model.manifest)
        if turn.status == "partial":
            result = AgentTurnResult.model_validate(turn.result)
            retry_source_ids = sorted(
                {
                    str(error.details["source_id"])
                    for error in result.retryable_errors
                    if error.details.get("source_id")
                }
            )
            if not retry_source_ids:
                return turn
            manifest["retry_source_ids"] = retry_source_ids
        if turn.status in {"failed", "cancelled", "partial"}:
            manifest["retry_count"] = int(
                manifest.get("retry_count", 0)
            ) + 1
        elif payload is None:
            raise HTTPException(
                status_code=422,
                detail="AGENT_RESUME_PAYLOAD_REQUIRED",
            )
        model.manifest = manifest
        model.status = "queued"
        model.cancel_requested = False
        model.completed_at = None
        model.error = None
        session.commit()
        background_tasks.add_task(
            process_turn,
            request.app.state.session_factory,
            request.app.state.settings,
            request.app.state.model_configuration,
            request.app.state.agent_checkpointer,
            turn_id,
            model_id,
            (
                payload.model_dump(exclude_none=True)
                if turn.status
                in {"waiting_input", "waiting_approval"}
                and payload is not None
                else None
            ),
        )
    return AgentTurnService(session).read(turn_id)


@router.get(
    "/agent-conversations",
    response_model=list[AgentConversationSummary],
)
def list_conversations(
    scope: Literal["active", "archived", "deleted"] = "active",
    q: str | None = None,
    session: Session = Depends(get_session),
) -> list[AgentConversationSummary]:
    return AgentConversationService(session).list(
        scope=scope,
        search=q,
    )


@router.post(
    "/agent-conversations",
    response_model=AgentConversationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation(
    payload: AgentConversationCreate,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    return AgentConversationService(session).create(payload)


@router.get(
    "/agent-conversations/current",
    response_model=AgentConversationRead,
)
def get_current_conversation(
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    return AgentConversationService(session).read_current()


@router.get(
    "/agent-conversations/{conversation_id}",
    response_model=AgentConversationRead,
)
def get_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    try:
        return AgentConversationService(session).read(conversation_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch(
    "/agent-conversations/{conversation_id}",
    response_model=AgentConversationRead,
)
def update_conversation(
    conversation_id: str,
    payload: AgentConversationPatch,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    try:
        return AgentConversationService(session).update(
            conversation_id,
            payload,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/agent-conversations/{conversation_id}/archive",
    response_model=AgentConversationRead,
)
def archive_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    try:
        return AgentConversationService(session).archive(conversation_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post(
    "/agent-conversations/{conversation_id}/restore",
    response_model=AgentConversationRead,
)
def restore_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    try:
        return AgentConversationService(session).restore(conversation_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete(
    "/agent-conversations/{conversation_id}",
    response_model=AgentConversationRead,
)
def delete_conversation(
    conversation_id: str,
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    try:
        return AgentConversationService(session).soft_delete(
            conversation_id
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/agent-runs", response_model=AgentRunResponse)
def run_agent(
    payload: AgentRunRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentRunResponse:
    artifacts = ArtifactService(
        session,
        request.app.state.settings.artifact_root,
        request.app.state.settings.artifact_max_bytes,
    )
    try:
        for artifact_id in payload.artifact_ids:
            artifacts.get(artifact_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    agent = WorkspaceAgentService(
        build_capability_executor(session, request.app.state.settings),
        request.app.state.model_configuration,
        request.app.state.model_chat,
    )
    try:
        return AgentConversationService(session).run_turn(payload, agent)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AgentTurnInProgressError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get(
    "/capability-invocations",
    response_model=list[CapabilityInvocationRead],
)
def list_invocations(
    session: Session = Depends(get_session),
) -> list[CapabilityInvocationRead]:
    invocations = session.scalars(
        select(CapabilityInvocationModel).order_by(
            CapabilityInvocationModel.started_at.desc()
        )
    )
    return [
        CapabilityInvocationRead.model_validate(invocation)
        for invocation in invocations
    ]
