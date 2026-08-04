from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.agent_runtime.service import WorkspaceAgentService
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.dependencies import get_session
from ai_signal_api.models import CapabilityInvocationModel
from ai_signal_api.modules.agent.conversation_service import (
    AgentConversationService,
    AgentTurnInProgressError,
)
from ai_signal_api.schemas import (
    AgentConversationRead,
    AgentRunRequest,
    AgentRunResponse,
    CapabilityInvocationRead,
)


router = APIRouter(prefix="/api", tags=["agent"])


@router.get(
    "/agent-conversations/current",
    response_model=AgentConversationRead,
)
def get_current_conversation(
    session: Session = Depends(get_session),
) -> AgentConversationRead:
    return AgentConversationService(session).read_current()


@router.post("/agent-runs", response_model=AgentRunResponse)
def run_agent(
    payload: AgentRunRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentRunResponse:
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
