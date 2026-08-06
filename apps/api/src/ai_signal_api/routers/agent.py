from typing import Literal
from uuid import uuid4

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
    AgentMessageModel,
    AgentTurnEventModel,
    AgentTurnModel,
    CapabilityInvocationModel,
)
from ai_signal_api.modules.agent.conversation_service import (
    AgentConversationService,
)
from ai_signal_api.modules.agent_assets.artifacts import ArtifactService
from ai_signal_api.modules.models.service import ModelConfigurationError
from ai_signal_api.schemas import (
    AgentConversationCreate,
    AgentConversationPatch,
    AgentConversationRead,
    AgentConversationSummary,
    AgentCapabilityCall,
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
    artifacts = ArtifactService(
        session,
        request.app.state.settings.artifact_root,
        request.app.state.settings.artifact_max_bytes,
    )
    try:
        attached_artifacts = [
            artifacts.get(artifact_id)
            for artifact_id in payload.artifact_ids
        ]
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
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
        image_artifact_ids = [
            artifact.id
            for artifact in attached_artifacts
            if artifact.media_type.startswith("image/")
        ]
        if image_artifact_ids:
            try:
                AgentTurnService(session).complete_direct_response(
                    turn.id,
                    model_service=request.app.state.model_configuration,
                    model_chat=request.app.state.model_chat,
                    model_id=payload.model_id,
                    image_urls=[
                        artifacts.image_data_url(artifact_id)
                        for artifact_id in image_artifact_ids
                    ],
                )
            except ValueError as error:
                raise HTTPException(
                    status_code=422,
                    detail=str(error),
                ) from error
            turn = AgentTurnService(session).read(turn.id)
        else:
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
    try:
        conversation_id = payload.conversation_id
        if conversation_id is None:
            conversation_id = AgentConversationService(
                session
            ).read_current().id
        executor = build_capability_executor(
            session,
            request.app.state.settings,
        )
        invalid_model_error: ModelConfigurationError | None = None
        execution_model_id = payload.model_id
        if not payload.image_urls:
            try:
                request.app.state.model_configuration.select_for_request(
                    payload.model_id
                )
            except ModelConfigurationError as error:
                invalid_model_error = error
                execution_model_id = None
        turn, created = AgentTurnService(session).create(
            conversation_id,
            AgentTurnCreate(
                message=payload.message,
                client_message_id=(
                    payload.client_message_id
                    or f"legacy-{uuid4().hex}"
                ),
                model_id=payload.model_id,
                artifact_ids=payload.artifact_ids,
            ),
            capability_ids=executor.registry.ids(),
        )
        if created:
            if payload.image_urls:
                AgentTurnService(session).complete_direct_response(
                    turn.id,
                    model_service=request.app.state.model_configuration,
                    model_chat=request.app.state.model_chat,
                    model_id=payload.model_id,
                    image_urls=payload.image_urls,
                )
            else:
                process_turn(
                    request.app.state.session_factory,
                    request.app.state.settings,
                    request.app.state.model_configuration,
                    request.app.state.agent_checkpointer,
                    turn.id,
                    execution_model_id,
                )
        session.expire_all()
        turn = AgentTurnService(session).read(turn.id)
        messages = list(
            session.scalars(
                select(AgentMessageModel).where(
                    AgentMessageModel.turn_id == turn.id
                )
            )
        )
        user_message = next(
            (item for item in messages if item.role == "user"),
            None,
        )
        assistant_message = next(
            (item for item in messages if item.role == "assistant"),
            None,
        )
        result = turn.result or {
            "status": turn.status,
            "errors": [turn.error] if turn.error else [],
        }
        result_errors = result.get("errors", [])
        if any(
            item.get("code") == "CAPABILITY_DISABLED"
            for item in result_errors
        ):
            raise HTTPException(
                status_code=403,
                detail="CAPABILITY_DISABLED",
            )
        compatibility_result = result
        steps = turn.plan.get("steps", [])
        deterministic_compatibility = (
            len(steps) == 1
            and steps[0].get("capability_id")
            in {
                "collection.run.start",
                "intelligence.timeline.query",
                "review.batch.submit",
                "poster.draft.generate",
                "task.draft.propose",
            }
        )
        if invalid_model_error is not None and not deterministic_compatibility:
            return AgentRunResponse(
                message=str(invalid_model_error),
                capability_calls=[],
                result={
                    "status": "failed",
                    "error_code": invalid_model_error.code,
                },
                requested_model_id=payload.model_id,
                effective_model_id=None,
                model_switched=False,
                conversation_id=turn.conversation_id,
                user_message_id=(
                    user_message.id if user_message is not None else None
                ),
                assistant_message_id=(
                    assistant_message.id
                    if assistant_message is not None
                    else None
                ),
            )
        if len(steps) == 1:
            capability_result = result.get(
                "capability_results",
                {},
            ).get(steps[0].get("step_id"))
            if capability_result is not None:
                compatibility_result = capability_result
        schedule_draft = (
            compatibility_result.get("schedule_draft")
            if isinstance(compatibility_result, dict)
            else None
        )
        task_draft = (
            compatibility_result.get("task_draft")
            if isinstance(compatibility_result, dict)
            else None
        )
        return AgentRunResponse(
            message=(
                assistant_message.content
                if assistant_message is not None
                else "任务未完成，请查看可定位错误。"
            ),
            capability_calls=[
                AgentCapabilityCall(
                    capability_id=str(step.get("capability_id")),
                    status=str(
                        result.get("capability_results", {})
                        .get(step.get("step_id"), {})
                        .get("status", "completed")
                    ),
                )
                for step in turn.plan.get("steps", [])
                if step.get("capability_id") != "agent.message.complete"
            ],
            result=compatibility_result,
            schedule_draft=schedule_draft,
            task_draft=task_draft,
            requested_model_id=turn.requested_model_id,
            effective_model_id=turn.effective_model_id,
            model_switched=bool(
                turn.requested_model_id
                and turn.requested_model_id != turn.effective_model_id
            ),
            conversation_id=turn.conversation_id,
            user_message_id=(
                user_message.id if user_message is not None else None
            ),
            assistant_message_id=(
                assistant_message.id
                if assistant_message is not None
                else None
            ),
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
