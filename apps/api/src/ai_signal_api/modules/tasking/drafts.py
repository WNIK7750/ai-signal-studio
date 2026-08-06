from __future__ import annotations

import re

from ai_signal_api.capabilities.product_schemas import (
    TaskDraftProposalInput,
    TaskDraftProposalResult,
)
from ai_signal_api.schemas import (
    AgentTaskDraft,
    ScheduleDraft,
    TaskConfig,
    TaskDelivery,
    TaskMatching,
    TaskQuantity,
    TaskSchedule,
    TaskSourceSelection,
)


class TaskDraftService:
    """Build a reviewable task proposal without creating a scheduled task."""

    def propose(
        self,
        input_data: TaskDraftProposalInput,
    ) -> TaskDraftProposalResult:
        message = input_data.message
        time_match = re.search(
            r"(?:上午|下午)?\s*(\d{1,2})\s*(?:点|:)(\d{2})?",
            message,
        )
        hour = int(time_match.group(1)) if time_match else 9
        minute = int(time_match.group(2) or 0) if time_match else 0
        if "下午" in message and hour < 12:
            hour += 12
        topics = self._extract_topics(message)
        schedule_draft = ScheduleDraft(
            frequency="daily",
            time_of_day=f"{hour:02d}:{minute:02d}",
            plan_name=f"每日 {topics[0] if topics != ['AI'] else 'AI'} 信息",
        )
        task_config = TaskConfig(
            sources=TaskSourceSelection(mode="all_enabled"),
            matching=TaskMatching(
                topics=topics,
                include_any=topics,
            ),
            quantity=self._extract_quantity(message),
            schedule=TaskSchedule(
                mode="daily",
                time_of_day=schedule_draft.time_of_day,
            ),
            delivery=TaskDelivery(
                summary_max_chars=self._extract_summary_limit(message),
            ),
        )
        cleaned_goal = re.sub(r"\s+", " ", message).strip()
        if len(cleaned_goal) > 180:
            cleaned_goal = f"{cleaned_goal[:177]}..."
        return TaskDraftProposalResult(
            schedule_draft=schedule_draft,
            task_draft=AgentTaskDraft(
                name=schedule_draft.plan_name,
                goal=cleaned_goal,
                status="draft",
                config=task_config.model_dump(mode="json"),
            ),
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
        return TaskQuantity(
            min_items=minimum,
            target_items=min(max(target, minimum), maximum),
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
