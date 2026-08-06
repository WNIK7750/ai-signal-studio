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
    AgentTaskDraft,
    CollectionRunStart,
    CardGenerateInput,
    ExecutionContext,
    ReviewSubmitInput,
    ScheduleDraft,
    TaskConfig,
    TaskDelivery,
    TaskMatching,
    TaskQuantity,
    TaskSchedule,
    TaskSourceSelection,
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
        if any(
            keyword in message
            for keyword in ("每天", "定时", "创建任务", "监测任务")
        ):
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
                plan_name=self._task_name(message),
            )
            task_config = TaskConfig(
                sources=TaskSourceSelection(mode="all_enabled"),
                matching=TaskMatching(
                    topics=self._extract_topics(message),
                    include_any=self._extract_topics(message),
                ),
                quantity=self._extract_quantity(message),
                schedule=TaskSchedule(
                    mode="daily",
                    time_of_day=draft.time_of_day,
                ),
                delivery=TaskDelivery(
                    summary_max_chars=self._extract_summary_limit(message),
                ),
            )
            task_draft = AgentTaskDraft(
                name=draft.plan_name,
                goal=self._task_goal(message),
                status="draft",
                config=task_config.model_dump(mode="json"),
            )
            return AgentRunResponse(
                message=(
                    "已整理为可编辑的任务草稿。"
                    "请检查来源、数量和时间，确认后再创建任务。"
                ),
                capability_calls=[],
                result={"status": "pending_confirmation"},
                schedule_draft=draft,
                task_draft=task_draft,
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

    @staticmethod
    def _extract_topics(message: str) -> list[str]:
        known_topics = (
            "OpenAI",
            "Anthropic",
            "Gemini",
            "LangGraph",
            "Agent",
            "AI Coding",
            "大模型",
            "多模态",
        )
        topics = [
            topic
            for topic in known_topics
            if topic.lower() in message.lower()
        ]
        return topics or ["AI"]

    @staticmethod
    def _extract_quantity(message: str) -> TaskQuantity:
        minimum_match = re.search(
            r"(?:至少|最少|下限)\s*(\d{1,3})\s*条?",
            message,
        )
        maximum_match = re.search(
            r"(?:最多|最大|上限)\s*(\d{1,3})\s*条?",
            message,
        )
        target_match = re.search(
            r"(?:目标|大约|约)\s*(\d{1,3})\s*条?",
            message,
        )
        minimum = int(minimum_match.group(1)) if minimum_match else 5
        maximum = int(maximum_match.group(1)) if maximum_match else 30
        if maximum < minimum:
            maximum = minimum
        target = (
            int(target_match.group(1))
            if target_match
            else min(max(minimum, 10), maximum)
        )
        target = min(max(target, minimum), maximum)
        return TaskQuantity(
            min_items=minimum,
            target_items=target,
            max_items=maximum,
        )

    @staticmethod
    def _extract_summary_limit(message: str) -> int:
        match = re.search(
            r"(?:摘要|内容|正文)?\s*(?:最多|上限|限制)"
            r"\s*(\d{3,4})\s*字",
            message,
        )
        if match is None:
            return 400
        return min(max(int(match.group(1)), 100), 1000)

    @staticmethod
    def _task_name(message: str) -> str:
        topics = WorkspaceAgentService._extract_topics(message)
        primary = topics[0] if topics != ["AI"] else "AI"
        return f"每日 {primary} 信息"

    @staticmethod
    def _task_goal(message: str) -> str:
        cleaned = re.sub(r"\s+", " ", message).strip()
        if len(cleaned) <= 180:
            return cleaned
        return f"{cleaned[:177]}..."


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
