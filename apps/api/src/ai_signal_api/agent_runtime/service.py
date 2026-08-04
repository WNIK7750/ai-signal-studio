from __future__ import annotations

import re
from typing import Any

from ai_signal_api.capabilities.core import CapabilityExecutor
from ai_signal_api.integrations.llm.chat import ModelChat
from ai_signal_api.modules.models.service import (
    ModelConfigurationError,
    ModelConfigurationService,
    ResolvedModel,
)
from ai_signal_api.schemas import (
    AgentCapabilityCall,
    AgentRunResponse,
    CollectionRunStart,
    CardGenerateInput,
    ExecutionContext,
    ReviewSubmitInput,
    ScheduleDraft,
    TimelineQuery,
)


class WorkspaceAgentService:
    def __init__(
        self,
        executor: CapabilityExecutor,
        model_service: ModelConfigurationService,
        model_chat: ModelChat,
    ) -> None:
        self.executor = executor
        self.model_service = model_service
        self.model_chat = model_chat

    def run(
        self,
        message: str,
        context: ExecutionContext,
        *,
        model_id: str | None = None,
        image_urls: list[str] | None = None,
    ) -> AgentRunResponse:
        images = image_urls or []
        if not images:
            action_response = self._run_action(message, context)
            if action_response is not None:
                return action_response.model_copy(
                    update={"requested_model_id": model_id}
                )

        try:
            selection = self.model_service.select_for_request(
                model_id,
            )
        except ModelConfigurationError as error:
            return AgentRunResponse(
                message=str(error),
                capability_calls=[],
                result={"status": "failed", "error_code": error.code},
                requested_model_id=model_id,
            )

        if images and not selection.effective_model.supports_vision:
            error = ModelConfigurationError("MODEL-002")
            return AgentRunResponse(
                message=str(error),
                capability_calls=[],
                result={"status": "failed", "error_code": error.code},
                requested_model_id=selection.requested_model_id,
                effective_model_id=selection.effective_model.id,
                model_switched=False,
            )

        try:
            response = self._run_message(
                message,
                context,
                selection.effective_model,
                images,
            )
        except ModelConfigurationError as error:
            return AgentRunResponse(
                message=str(error),
                capability_calls=[],
                result={"status": "failed", "error_code": error.code},
                requested_model_id=selection.requested_model_id,
                effective_model_id=selection.effective_model.id,
                model_switched=selection.switched,
            )
        return response.model_copy(
            update={
                "requested_model_id": selection.requested_model_id,
                "effective_model_id": selection.effective_model.id,
                "model_switched": selection.switched,
            }
        )

    def _run_action(
        self,
        message: str,
        context: ExecutionContext,
    ) -> AgentRunResponse | None:
        if "每天" in message or "定时" in message:
            time_match = re.search(
                r"(?:上午|下午)?\s*(\d{1,2})\s*(?:点|:)(\d{2})?",
                message,
            )
            hour = int(time_match.group(1)) if time_match else 9
            minute = int(time_match.group(2) or 0) if time_match else 0
            if "下午" in message and hour < 12:
                hour += 12
            draft = ScheduleDraft(
                frequency="daily",
                time_of_day=f"{hour:02d}:{minute:02d}",
                plan_name="每日 AI 要闻",
            )
            return AgentRunResponse(
                message="已准备定时任务，请确认时间和方案。",
                capability_calls=[],
                result={"status": "pending_confirmation"},
                schedule_draft=draft,
            )

        if any(keyword in message for keyword in ("采集", "收集", "更新")):
            output = self.executor.execute(
                "collection.run.start",
                CollectionRunStart(),
                context,
            )
            error_code = self._collection_error_code(output.errors)
            if output.status == "failed":
                message_text = (
                    "采集未完成：当前没有启用的信息来源。"
                    if error_code == "NO_ENABLED_SOURCES"
                    else (
                        f"采集未完成，{len(output.errors)} 个来源失败。"
                        "请在运行记录中查看原因。"
                    )
                )
            elif output.status == "partial":
                message_text = (
                    f"采集部分完成，新增 {output.items_added} 条；"
                    f"{len(output.errors)} 个来源失败。"
                )
            elif output.items_added == 0:
                message_text = (
                    "采集完成，本次没有新增 AI 信息"
                    "（已有内容已自动去重）。"
                )
            else:
                message_text = (
                    f"采集完成，新增 {output.items_added} 条 AI 信息。"
                )
            return AgentRunResponse(
                message=message_text,
                capability_calls=[
                    AgentCapabilityCall(
                        capability_id="collection.run.start",
                        status=output.status,
                    )
                ],
                result={
                    **output.model_dump(mode="json"),
                    **(
                        {"error_code": error_code}
                        if output.status == "failed" and error_code
                        else {}
                    ),
                },
            )

        if "审核" in message and any(
            keyword in message for keyword in ("保留", "通过", "确认")
        ):
            output = self.executor.execute(
                "review.batch.submit",
                ReviewSubmitInput(
                    default_decision="keep",
                    confirm=True,
                ),
                context,
            )
            return AgentRunResponse(
                message=f"已确认 {len(output.items)} 条审核决定。",
                capability_calls=[
                    AgentCapabilityCall(
                        capability_id="review.batch.submit",
                        status=output.status,
                    )
                ],
                result=output.model_dump(mode="json"),
            )

        if "卡片" in message and any(
            keyword in message for keyword in ("生成", "整理", "制作")
        ):
            output = self.executor.execute(
                "poster.draft.generate",
                CardGenerateInput(),
                context,
            )
            return AgentRunResponse(
                message=f"已生成 {output.created} 张卡片。",
                capability_calls=[
                    AgentCapabilityCall(
                        capability_id="poster.draft.generate",
                        status="completed",
                    )
                ],
                result=output.model_dump(mode="json"),
            )

        return None

    def _run_message(
        self,
        message: str,
        context: ExecutionContext,
        model: ResolvedModel,
        image_urls: list[str],
    ) -> AgentRunResponse:
        if image_urls:
            return self._complete_with_model(model, message, image_urls)

        if (
            model.provider == "openai_compatible"
            and not any(
                keyword in message
                for keyword in ("查询", "查找", "时间线", "信息")
            )
        ):
            return self._complete_with_model(model, message, [])

        search = self._extract_search(message)
        output = self.executor.execute(
            "intelligence.timeline.query",
            TimelineQuery(search=search),
            context,
        )
        return AgentRunResponse(
            message=f"找到 {output.total} 条相关 AI 信息。",
            capability_calls=[
                AgentCapabilityCall(
                    capability_id="intelligence.timeline.query",
                    status="completed",
                )
            ],
            result=output.model_dump(mode="json"),
        )

    @staticmethod
    def _collection_error_code(
        errors: list[dict[str, Any]],
    ) -> str | None:
        if not errors:
            return None
        error_code = errors[0].get("error_code")
        return error_code if isinstance(error_code, str) else None

    def _complete_with_model(
        self,
        model: ResolvedModel,
        message: str,
        image_urls: list[str],
    ) -> AgentRunResponse:
        content = self.model_chat.complete(model, message, image_urls)
        return AgentRunResponse(
            message=content,
            capability_calls=[],
            result={
                "status": "completed",
                "model_id": model.id,
            },
        )

    @staticmethod
    def _extract_search(message: str) -> str | None:
        known_topics = (
            "LangGraph",
            "OpenAI",
            "Agent",
            "WebSocket",
            "Whisper",
        )
        return next(
            (topic for topic in known_topics if topic.lower() in message.lower()),
            None,
        )


def as_langchain_tool_payload(
    capability_id: str,
    result: Any,
) -> dict[str, Any]:
    """Small adapter boundary shared by future LangChain StructuredTools."""
    return {
        "capability_id": capability_id,
        "result": (
            result.model_dump(mode="json")
            if hasattr(result, "model_dump")
            else result
        ),
    }
