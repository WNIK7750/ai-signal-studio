from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_signal_api.agent_runtime.service import WorkspaceAgentService
from ai_signal_api.capabilities.core import CapabilityExecutionError
from ai_signal_api.models import (
    AgentConversationModel,
    AgentMessageModel,
)
from ai_signal_api.schemas import (
    AgentConversationRead,
    AgentMessageRead,
    AgentRunRequest,
    AgentRunResponse,
    ExecutionContext,
)


class AgentTurnInProgressError(RuntimeError):
    pass


class AgentConversationService:
    """Owns durable local conversations and idempotent Agent turns."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def read_current(self) -> AgentConversationRead:
        conversation = self._get_or_create_current()
        messages = list(
            self.session.scalars(
                select(AgentMessageModel)
                .where(
                    AgentMessageModel.conversation_id == conversation.id
                )
                .order_by(
                    AgentMessageModel.created_at,
                    AgentMessageModel.id,
                )
                .limit(200)
            )
        )
        return AgentConversationRead(
            id=conversation.id,
            title=conversation.title,
            status=conversation.status,
            messages=[
                AgentMessageRead.model_validate(message)
                for message in messages
            ],
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )

    def run_turn(
        self,
        payload: AgentRunRequest,
        agent: WorkspaceAgentService,
    ) -> AgentRunResponse:
        conversation = self._resolve_conversation(payload.conversation_id)
        client_message_id = (
            payload.client_message_id or f"client_{uuid4().hex}"
        )
        existing_user = self.session.scalar(
            select(AgentMessageModel).where(
                AgentMessageModel.conversation_id == conversation.id,
                AgentMessageModel.role == "user",
                AgentMessageModel.client_message_id == client_message_id,
            )
        )
        if existing_user is not None:
            existing_assistant = self.session.scalar(
                select(AgentMessageModel).where(
                    AgentMessageModel.conversation_id == conversation.id,
                    AgentMessageModel.role == "assistant",
                    AgentMessageModel.request_id == existing_user.request_id,
                )
            )
            if existing_assistant is None:
                raise AgentTurnInProgressError("AGENT_TURN_IN_PROGRESS")
            return self._response_from_message(
                conversation.id,
                existing_user.id,
                existing_assistant,
            )

        request_id = f"req_{uuid4().hex}"
        user_message = AgentMessageModel(
            conversation_id=conversation.id,
            role="user",
            content=payload.message,
            client_message_id=client_message_id,
            request_id=request_id,
            image_count=len(payload.image_urls),
        )
        self.session.add(user_message)
        self._touch(conversation)
        self.session.commit()

        context = ExecutionContext(
            request_id=request_id,
            actor_type="internal_agent",
            actor_id="workspace-agent",
            idempotency_key=client_message_id,
        )
        try:
            response = agent.run(
                payload.message,
                context,
                model_id=payload.model_id,
                image_urls=payload.image_urls,
            )
        except CapabilityExecutionError as error:
            self._save_assistant(
                conversation,
                request_id,
                AgentRunResponse(
                    message=f"{error.code}（Agent 能力当前不可用）",
                    capability_calls=[],
                    result={
                        "status": "failed",
                        "error_code": error.code,
                    },
                    requested_model_id=payload.model_id,
                ),
                error_code=error.code,
            )
            raise
        except Exception:
            self._save_assistant(
                conversation,
                request_id,
                AgentRunResponse(
                    message="SYS-001（Agent 执行失败，请查看运行记录）",
                    capability_calls=[],
                    result={
                        "status": "failed",
                        "error_code": "AGENT_EXECUTION_FAILED",
                    },
                    requested_model_id=payload.model_id,
                ),
                error_code="AGENT_EXECUTION_FAILED",
            )
            raise

        assistant_message = self._save_assistant(
            conversation,
            request_id,
            response,
            error_code=self._response_error_code(response),
        )
        return response.model_copy(
            update={
                "conversation_id": conversation.id,
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
            }
        )

    def _get_or_create_current(self) -> AgentConversationModel:
        conversation = self.session.scalar(
            select(AgentConversationModel)
            .where(AgentConversationModel.status == "active")
            .order_by(AgentConversationModel.updated_at.desc())
        )
        if conversation is not None:
            return conversation
        conversation = AgentConversationModel()
        self.session.add(conversation)
        self.session.commit()
        return conversation

    def _resolve_conversation(
        self,
        conversation_id: str | None,
    ) -> AgentConversationModel:
        if conversation_id is None:
            return self._get_or_create_current()
        conversation = self.session.get(
            AgentConversationModel,
            conversation_id,
        )
        if conversation is None or conversation.status != "active":
            raise LookupError("AGENT_CONVERSATION_NOT_FOUND")
        return conversation

    def _save_assistant(
        self,
        conversation: AgentConversationModel,
        request_id: str,
        response: AgentRunResponse,
        *,
        error_code: str | None,
    ) -> AgentMessageModel:
        assistant = AgentMessageModel(
            conversation_id=conversation.id,
            role="assistant",
            content=response.message,
            request_id=request_id,
            capability_calls=[
                call.model_dump(mode="json")
                for call in response.capability_calls
            ],
            result_data=response.result,
            schedule_draft=(
                response.schedule_draft.model_dump(mode="json")
                if response.schedule_draft is not None
                else None
            ),
            requested_model_id=response.requested_model_id,
            effective_model_id=response.effective_model_id,
            model_switched=response.model_switched,
            error_code=error_code,
        )
        self.session.add(assistant)
        self._touch(conversation)
        self.session.commit()
        return assistant

    @staticmethod
    def _touch(conversation: AgentConversationModel) -> None:
        conversation.updated_at = datetime.now(timezone.utc)

    @staticmethod
    def _response_error_code(response: AgentRunResponse) -> str | None:
        error_code = response.result.get("error_code")
        if isinstance(error_code, str):
            return error_code
        if response.result.get("status") != "failed":
            return None
        errors = response.result.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            value = errors[0].get("error_code")
            if isinstance(value, str):
                return value
        return "AGENT_ACTION_FAILED"

    @staticmethod
    def _response_from_message(
        conversation_id: str,
        user_message_id: str,
        assistant: AgentMessageModel,
    ) -> AgentRunResponse:
        return AgentRunResponse(
            message=assistant.content,
            capability_calls=assistant.capability_calls,
            result=assistant.result_data,
            schedule_draft=assistant.schedule_draft,
            requested_model_id=assistant.requested_model_id,
            effective_model_id=assistant.effective_model_id,
            model_switched=assistant.model_switched,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant.id,
        )
