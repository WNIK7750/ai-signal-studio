from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel

from ai_signal_api.capabilities.core import CapabilityExecutor
from ai_signal_api.capabilities.product_schemas import (
    AppearanceActionInput,
    CardGetInput,
    CardQueryInput,
    ConversationIdInput,
    ConversationListInput,
    ConversationPatchCapabilityInput,
    EmptyInput,
    InformationStateCapabilityInput,
    ModelSelectionInput,
    RunGetInput,
    RunListInput,
    SourcePatchCapabilityInput,
    SourceTestInput,
    TaskGetInput,
    TaskPatchCapabilityInput,
    TaskDraftProposalInput,
)
from ai_signal_api.modules.agent_assets.schemas import (
    AgentPackSearchInput,
    ArtifactSearchInput,
)
from ai_signal_api.modules.intelligence.agent.schemas import (
    InformationRecommendInput,
    ResearchInput,
)
from ai_signal_api.modules.intelligence.search import IntelligenceSearchInput
from ai_signal_api.modules.collection.web_discovery import (
    WebSearchCollectInput,
)
from ai_signal_api.schemas import (
    CardRenderCapabilityInput,
    CardUpdateCapabilityInput,
    CollectionRunStart,
    ExecutionContext,
    TimelineQuery,
    CardGenerateInput,
    ReviewSubmitInput,
    TaskRunCapabilityInput,
)


TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "collection.run.start": CollectionRunStart,
    "web.search.collect": WebSearchCollectInput,
    "intelligence.search": IntelligenceSearchInput,
    "intelligence.timeline.query": TimelineQuery,
    "intelligence.recommend": InformationRecommendInput,
    "research.filter": ResearchInput,
    "research.recommend": ResearchInput,
    "research.match_requirements": ResearchInput,
    "research.compare": ResearchInput,
    "research.trend_brief": ResearchInput,
    "research.coverage_gap": ResearchInput,
    "agent_pack.search": AgentPackSearchInput,
    "artifact.search": ArtifactSearchInput,
    "poster.card.update": CardUpdateCapabilityInput,
    "poster.card.render": CardRenderCapabilityInput,
    "poster.draft.generate": CardGenerateInput,
    "review.batch.submit": ReviewSubmitInput,
    "task.run.start": TaskRunCapabilityInput,
    "task.draft.propose": TaskDraftProposalInput,
    "source.list": EmptyInput,
    "source.test": SourceTestInput,
    "source.update": SourcePatchCapabilityInput,
    "task.list": EmptyInput,
    "task.get": TaskGetInput,
    "task.update": TaskPatchCapabilityInput,
    "run.list": RunListInput,
    "run.get": RunGetInput,
    "card.list": CardQueryInput,
    "card.get": CardGetInput,
    "information.state.update": InformationStateCapabilityInput,
    "model.list": EmptyInput,
    "model.select": ModelSelectionInput,
    "conversation.list": ConversationListInput,
    "conversation.update": ConversationPatchCapabilityInput,
    "conversation.archive": ConversationIdInput,
    "conversation.restore": ConversationIdInput,
    "appearance.set": AppearanceActionInput,
}

PLANNING_CAPABILITY_CONTRACTS: dict[str, dict[str, str]] = {
    "collection.run.start": {
        "kind": "capability",
        "domain": "collection",
        "side_effect": "external",
        "risk": "low",
        "acceptance_policy": "capability_effect.v1",
    },
    "web.search.collect": {
        "kind": "capability",
        "domain": "collection",
        "side_effect": "external",
        "risk": "low",
        "acceptance_policy": "capability_effect.v1",
    },
    "intelligence.search": {
        "kind": "capability",
        "domain": "intelligence",
        "side_effect": "read",
        "risk": "low",
        "acceptance_policy": "information_results.v1",
    },
    "intelligence.timeline.query": {
        "kind": "capability",
        "domain": "intelligence",
        "side_effect": "read",
        "risk": "low",
        "acceptance_policy": "information_results.v1",
    },
    "research.recommend": {
        "kind": "domain_agent",
        "domain": "intelligence",
        "side_effect": "read",
        "risk": "low",
        "acceptance_policy": "information_results.v1",
    },
    "research.trend_brief": {
        "kind": "domain_agent",
        "domain": "intelligence",
        "side_effect": "read",
        "risk": "low",
        "acceptance_policy": "synthesis_grounded.v1",
    },
}


def build_capability_tool(
    executor: CapabilityExecutor,
    capability_id: str,
    context_factory: Callable[[], ExecutionContext],
) -> BaseTool:
    schema = TOOL_SCHEMAS[capability_id]

    def execute(**values: Any) -> dict[str, Any]:
        output = executor.execute(
            capability_id,
            schema.model_validate(values),
            context_factory(),
        )
        return output.model_dump(mode="json")

    return StructuredTool.from_function(
        func=execute,
        name=capability_id.replace(".", "_"),
        description=f"Execute the registered {capability_id} capability.",
        args_schema=schema,
    )
