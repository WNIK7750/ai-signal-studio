from sqlalchemy.orm import Session

from ai_signal_api.capabilities.core import (
    CapabilityExecutor,
    CapabilityRegistry,
)
from ai_signal_api.config import Settings
from ai_signal_api.modules.cards.service import CardService
from ai_signal_api.modules.collection.service import CollectionService
from ai_signal_api.modules.intelligence.llm_analyzer import build_analyzer
from ai_signal_api.modules.intelligence.timeline import TimelineService
from ai_signal_api.modules.review.service import ReviewService
from ai_signal_api.schemas import (
    CardGenerateInput,
    CardGenerateResult,
    CollectionRunRead,
    CollectionRunStart,
    ExecutionContext,
    ReviewBatchRead,
    ReviewSubmitInput,
    TimelinePage,
    TimelineQuery,
)


def build_capability_executor(
    session: Session,
    settings: Settings,
) -> CapabilityExecutor:
    collection = CollectionService(
        session,
        analyzer=build_analyzer(settings),
    )
    timeline = TimelineService(session)
    review = ReviewService(session)
    cards = CardService(session, settings.timezone)
    registry = CapabilityRegistry()

    def start_collection(
        input_data: CollectionRunStart,
        _context: ExecutionContext,
    ) -> CollectionRunRead:
        return CollectionRunRead.model_validate(
            collection.start(input_data.source_ids)
        )

    def query_timeline(
        input_data: TimelineQuery,
        _context: ExecutionContext,
    ) -> TimelinePage:
        return timeline.query(input_data)

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

    registry.register("collection.run.start", start_collection)
    registry.register("intelligence.timeline.query", query_timeline)
    registry.register("review.batch.submit", submit_review)
    registry.register("poster.draft.generate", generate_cards)
    return CapabilityExecutor(
        session,
        registry,
        disabled_capabilities=set(settings.disabled_capabilities),
    )
