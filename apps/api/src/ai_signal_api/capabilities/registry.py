from sqlalchemy.orm import Session

from ai_signal_api.capabilities.core import (
    CapabilityExecutor,
    CapabilityRegistry,
)
from ai_signal_api.config import Settings
from ai_signal_api.modules.cards.service import CardService
from ai_signal_api.modules.agent_assets.agent_packs import AgentPackService
from ai_signal_api.modules.agent_assets.artifacts import ArtifactService
from ai_signal_api.modules.agent_assets.schemas import (
    AgentPackSearchInput,
    AgentPackSearchResult,
    ArtifactSearchInput,
    ArtifactSearchResult,
)
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.modules.collection.service import SourceService
from ai_signal_api.modules.collection.web_discovery import (
    WebDiscoveryService,
    WebSearchCollectInput,
    WebSearchCollectResult,
)
from ai_signal_api.integrations.search.brave import BraveWebSearchProvider
from ai_signal_api.integrations.search.model import (
    FallbackWebSearchProvider,
    ModelWebSearchProvider,
)
from ai_signal_api.modules.agent.conversation_service import (
    AgentConversationService,
)
from ai_signal_api.modules.intelligence.library import (
    InformationLibraryService,
)
from ai_signal_api.modules.models.service import (
    build_model_configuration_service,
)
from ai_signal_api.capabilities.product_schemas import (
    AppearanceActionInput,
    CardGetInput,
    CardQueryInput,
    ClientActionResult,
    ConversationIdInput,
    ConversationListInput,
    ConversationListResult,
    ConversationPatchCapabilityInput,
    EmptyInput,
    InformationStateCapabilityInput,
    ModelListResult,
    ModelSelectionInput,
    RunGetInput,
    RunListInput,
    RunListResult,
    SourceListResult,
    SourcePatchCapabilityInput,
    SourceTestInput,
    TaskGetInput,
    TaskListResult,
    TaskPatchCapabilityInput,
    TaskDraftProposalInput,
    TaskDraftProposalResult,
)
from ai_signal_api.modules.intelligence.llm_analyzer import build_analyzer
from ai_signal_api.modules.intelligence.agent.schemas import (
    InformationRecommendInput,
    InformationRecommendResult,
    ResearchInput,
    ResearchResult,
)
from ai_signal_api.modules.intelligence.agent.research import ResearchService
from ai_signal_api.modules.intelligence.agent.service import (
    InformationRecommendationService,
)
from ai_signal_api.modules.intelligence.timeline import TimelineService
from ai_signal_api.modules.intelligence.search import (
    IntelligenceSearchInput,
    IntelligenceSearchResult,
    UnifiedIntelligenceSearchService,
)
from ai_signal_api.modules.review.service import ReviewService
from ai_signal_api.modules.tasking.service import TaskingService
from ai_signal_api.modules.tasking.drafts import TaskDraftService
from ai_signal_api.schemas import (
    CardGenerateInput,
    CardGenerateResult,
    CardRenderCapabilityInput,
    CardRenderResult,
    CardUpdateCapabilityInput,
    CardRead,
    CardPage,
    CollectionRunRead,
    SourceRead,
    SourceTestRead,
    TaskRead,
    WorkspaceItemStateRead,
    AgentConversationRead,
    ModelConfigRead,
    CollectionRunStart,
    ExecutionContext,
    ReviewBatchRead,
    ReviewSubmitInput,
    TimelinePage,
    TimelineQuery,
    TaskRunCapabilityInput,
    TaskRunRead,
)


def build_capability_executor(
    session: Session,
    settings: Settings,
) -> CapabilityExecutor:
    collection = CollectionService(
        session,
        analyzer=build_analyzer(settings),
    )
    model_configuration = build_model_configuration_service(settings)
    search_model = model_configuration.select_for_search()
    search_providers = []
    if search_model is not None:
        search_providers.append(
            ModelWebSearchProvider(
                search_model,
                timeout_seconds=settings.llm_timeout_seconds,
            )
        )
    if (
        settings.search_api_key is not None
        and settings.search_api_key.get_secret_value().strip()
    ):
        search_providers.append(
            BraveWebSearchProvider(
                settings.search_api_key.get_secret_value().strip(),
                base_url=settings.search_base_url,
            )
        )
    search_provider = (
        FallbackWebSearchProvider(search_providers)
        if len(search_providers) > 1
        else search_providers[0]
        if search_providers
        else None
    )
    web_discovery = WebDiscoveryService(
        session,
        collection,
        search_provider,
    )
    timeline = TimelineService(session)
    intelligence_search = UnifiedIntelligenceSearchService(session)
    recommendation = InformationRecommendationService(timeline)
    research = ResearchService(timeline, intelligence_search)
    review = ReviewService(session)
    cards = CardService(session, settings.timezone)
    tasking = TaskingService(session, collection)
    task_drafts = TaskDraftService()
    sources = SourceService(session)
    library = InformationLibraryService(session)
    conversations = AgentConversationService(session)
    agent_packs = AgentPackService(session, settings.agent_pack_root)
    artifacts = ArtifactService(
        session,
        settings.artifact_root,
        settings.artifact_max_bytes,
    )
    registry = CapabilityRegistry()

    def start_collection(
        input_data: CollectionRunStart,
        context: ExecutionContext,
    ) -> CollectionRunRead:
        return CollectionRunRead.model_validate(
            collection.start(
                input_data.source_ids,
                idempotency_key=context.idempotency_key,
                trigger_type=input_data.trigger_type,
            )
        )

    def query_timeline(
        input_data: TimelineQuery,
        _context: ExecutionContext,
    ) -> TimelinePage:
        return timeline.query(input_data)

    def search_intelligence(
        input_data: IntelligenceSearchInput,
        _context: ExecutionContext,
    ) -> IntelligenceSearchResult:
        return intelligence_search.search(input_data)

    def collect_web_search(
        input_data: WebSearchCollectInput,
        context: ExecutionContext,
    ) -> WebSearchCollectResult:
        return web_discovery.collect(
            input_data,
            idempotency_key=context.idempotency_key,
        )

    def recommend_information(
        input_data: InformationRecommendInput,
        _context: ExecutionContext,
    ) -> InformationRecommendResult:
        return recommendation.recommend(input_data)

    def execute_research(
        workflow: str,
        input_data: ResearchInput,
    ) -> ResearchResult:
        return research.execute(workflow, input_data)

    def submit_review(
        input_data: ReviewSubmitInput,
        context: ExecutionContext,
    ) -> ReviewBatchRead:
        return review.submit(input_data, context)

    def generate_cards(
        input_data: CardGenerateInput,
        _context: ExecutionContext,
    ) -> CardGenerateResult:
        return cards.generate(input_data)

    def update_card(
        input_data: CardUpdateCapabilityInput,
        _context: ExecutionContext,
    ) -> CardRead:
        return cards.update(
            input_data.card_id,
            input_data,
        )

    def render_card(
        input_data: CardRenderCapabilityInput,
        _context: ExecutionContext,
    ) -> CardRenderResult:
        return cards.render(
            input_data.card_id,
            artifact_root=settings.artifact_root,
            artifact_max_bytes=settings.artifact_max_bytes,
        )

    def start_task_run(
        input_data: TaskRunCapabilityInput,
        context: ExecutionContext,
    ) -> TaskRunRead:
        return tasking.run(
            input_data.task_id,
            task_version_id=input_data.task_version_id,
            trigger_type=input_data.trigger_type,
            idempotency_key=context.idempotency_key,
        )

    def search_agent_pack(
        input_data: AgentPackSearchInput,
        _context: ExecutionContext,
    ) -> AgentPackSearchResult:
        return AgentPackSearchResult(
            matches=agent_packs.search(
                input_data.pack_id,
                input_data.query,
            )
        )

    def search_artifacts(
        input_data: ArtifactSearchInput,
        _context: ExecutionContext,
    ) -> ArtifactSearchResult:
        return artifacts.search(input_data.query, input_data.limit)

    def list_sources(
        _input_data: EmptyInput,
        _context: ExecutionContext,
    ) -> SourceListResult:
        return SourceListResult(
            items=[SourceRead.model_validate(item) for item in sources.list()]
        )

    def test_source(
        input_data: SourceTestInput,
        _context: ExecutionContext,
    ) -> SourceTestRead:
        return SourceTestRead.model_validate(
            sources.test(input_data.source_id)
        )

    def patch_source(
        input_data: SourcePatchCapabilityInput,
        _context: ExecutionContext,
    ) -> SourceRead:
        return SourceRead.model_validate(
            sources.patch(
                input_data.source_id,
                input_data.model_dump(
                    exclude={"source_id"},
                    exclude_unset=True,
                ),
            )
        )

    def list_tasks(
        _input_data: EmptyInput,
        _context: ExecutionContext,
    ) -> TaskListResult:
        return TaskListResult(items=tasking.list_tasks())

    def get_task(
        input_data: TaskGetInput,
        _context: ExecutionContext,
    ) -> TaskRead:
        return tasking.get_task(input_data.task_id)

    def patch_task(
        input_data: TaskPatchCapabilityInput,
        _context: ExecutionContext,
    ) -> TaskRead:
        return tasking.patch_task(
            input_data.task_id,
            input_data,
        )

    def propose_task_draft(
        input_data: TaskDraftProposalInput,
        _context: ExecutionContext,
    ) -> TaskDraftProposalResult:
        return task_drafts.propose(input_data)

    def list_runs(
        input_data: RunListInput,
        _context: ExecutionContext,
    ) -> RunListResult:
        return RunListResult(
            items=[
                CollectionRunRead.model_validate(item)
                for item in collection.list_runs(input_data.limit)
            ]
        )

    def get_run(
        input_data: RunGetInput,
        _context: ExecutionContext,
    ) -> CollectionRunRead:
        return CollectionRunRead.model_validate(
            collection.get_run(input_data.run_id)
        )

    def query_cards(
        input_data: CardQueryInput,
        _context: ExecutionContext,
    ) -> CardPage:
        return cards.list(**input_data.model_dump())

    def get_card(
        input_data: CardGetInput,
        _context: ExecutionContext,
    ) -> CardRead:
        return cards.get(input_data.card_id)

    def update_information_state(
        input_data: InformationStateCapabilityInput,
        _context: ExecutionContext,
    ) -> WorkspaceItemStateRead:
        return library.update_state(input_data.item_id, input_data)

    def list_models(
        _input_data: EmptyInput,
        _context: ExecutionContext,
    ) -> ModelListResult:
        return ModelListResult(
            items=[
                ModelConfigRead.model_validate(item)
                for item in model_configuration.list_models()
            ]
        )

    def select_model(
        input_data: ModelSelectionInput,
        _context: ExecutionContext,
    ) -> ClientActionResult:
        model_configuration.select_for_request(input_data.model_id)
        return ClientActionResult(
            action="select_model",
            payload={"model_id": input_data.model_id},
        )

    def list_conversations(
        input_data: ConversationListInput,
        _context: ExecutionContext,
    ) -> ConversationListResult:
        return ConversationListResult(
            items=conversations.list(
                scope=input_data.scope,
                search=input_data.search,
            )
        )

    def patch_conversation(
        input_data: ConversationPatchCapabilityInput,
        _context: ExecutionContext,
    ) -> AgentConversationRead:
        return conversations.update(
            input_data.conversation_id,
            input_data,
        )

    def archive_conversation(
        input_data: ConversationIdInput,
        _context: ExecutionContext,
    ) -> AgentConversationRead:
        return conversations.archive(input_data.conversation_id)

    def restore_conversation(
        input_data: ConversationIdInput,
        _context: ExecutionContext,
    ) -> AgentConversationRead:
        return conversations.restore(input_data.conversation_id)

    def set_appearance(
        input_data: AppearanceActionInput,
        _context: ExecutionContext,
    ) -> ClientActionResult:
        return ClientActionResult(
            action="set_appearance",
            payload={"theme": input_data.theme},
        )

    registry.register("collection.run.start", start_collection)
    registry.register("web.search.collect", collect_web_search)
    registry.register("task.run.start", start_task_run)
    registry.register("task.draft.propose", propose_task_draft)
    registry.register("intelligence.timeline.query", query_timeline)
    registry.register("intelligence.search", search_intelligence)
    registry.register("intelligence.recommend", recommend_information)
    for workflow in (
        "research.filter",
        "research.recommend",
        "research.match_requirements",
        "research.compare",
        "research.trend_brief",
        "research.coverage_gap",
    ):
        registry.register(
            workflow,
            lambda input_data, _context, workflow=workflow: execute_research(
                workflow,
                input_data,
            ),
        )
    registry.register("review.batch.submit", submit_review)
    registry.register("poster.draft.generate", generate_cards)
    registry.register("poster.card.update", update_card)
    registry.register("poster.card.render", render_card)
    registry.register("agent_pack.search", search_agent_pack)
    registry.register("artifact.search", search_artifacts)
    registry.register("source.list", list_sources)
    registry.register("source.test", test_source)
    registry.register("source.update", patch_source)
    registry.register("task.list", list_tasks)
    registry.register("task.get", get_task)
    registry.register("task.update", patch_task)
    registry.register("run.list", list_runs)
    registry.register("run.get", get_run)
    registry.register("card.list", query_cards)
    registry.register("card.get", get_card)
    registry.register("information.state.update", update_information_state)
    registry.register("model.list", list_models)
    registry.register("model.select", select_model)
    registry.register("conversation.list", list_conversations)
    registry.register("conversation.update", patch_conversation)
    registry.register("conversation.archive", archive_conversation)
    registry.register("conversation.restore", restore_conversation)
    registry.register("appearance.set", set_appearance)
    return CapabilityExecutor(
        session,
        registry,
        disabled_capabilities=set(settings.disabled_capabilities),
    )
