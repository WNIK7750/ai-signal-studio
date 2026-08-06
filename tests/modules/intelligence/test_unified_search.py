from __future__ import annotations

from datetime import datetime, timezone

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.models import (
    CardModel,
    ReviewBatchModel,
    ReviewDecisionModel,
    WorkspaceItemStateModel,
)
from ai_signal_api.modules.intelligence.search import IntelligenceSearchInput
from ai_signal_api.schemas import ExecutionContext


def _seed_information(client):
    client.post(
        "/api/collection-runs",
        json={"source_ids": [], "trigger_type": "test"},
    )
    session = client.app.state.session_factory()
    items = build_capability_executor(
        session,
        client.app.state.settings,
    ).execute(
        "intelligence.search",
        IntelligenceSearchInput(query="", limit=10),
        ExecutionContext(
            request_id="search-seed",
            actor_type="internal_agent",
        ),
    ).items
    return session, items


def test_unified_search_returns_ranked_information_and_short_query(
    client,
) -> None:
    session, seeded = _seed_information(client)
    try:
        executor = build_capability_executor(
            session,
            client.app.state.settings,
        )
        result = executor.execute(
            "intelligence.search",
            IntelligenceSearchInput(
                query="AI",
                scopes=["intelligence"],
                limit=3,
            ),
            ExecutionContext(
                request_id="search-ai",
                actor_type="internal_agent",
            ),
        )
        assert seeded
        assert result.items
        assert result.algorithm == "fts5_bm25+rrf+simhash"
        assert all(item.information_id for item in result.items)
        assert all(item.ranking_signals for item in result.items)
        assert all(item.app_path.startswith("/timeline?focus=") for item in result.items)
    finally:
        session.close()


def test_unified_search_exposes_product_stage_facets_without_duplicates(
    client,
) -> None:
    session, seeded = _seed_information(client)
    try:
        first = seeded[0]
        second = seeded[1]
        batch = ReviewBatchModel(
            status="pending",
            item_ids=[first.information_id],
        )
        session.add(batch)
        session.flush()
        decision = ReviewDecisionModel(
            batch_id=batch.id,
            item_id=second.information_id,
            decision="approved",
        )
        session.add(decision)
        session.flush()
        session.add(
            CardModel(
                intelligence_item_id=second.information_id,
                review_decision_id=decision.id,
                title="统一检索卡片",
                summary="统一检索可以跨阶段复用同一条信息。",
                key_points=["检索", "去重"],
                source_name=second.source_name,
                source_kind="demo",
                canonical_url=second.source_url,
                published_at=second.published_at,
                priority=second.priority,
                topics=second.topics,
            )
        )
        session.add(
            WorkspaceItemStateModel(
                intelligence_item_id=first.information_id,
                archived_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        result = build_capability_executor(
            session,
            client.app.state.settings,
        ).execute(
            "intelligence.search",
            IntelligenceSearchInput(
                query="",
                scopes=["pending", "archived", "cards"],
                limit=10,
            ),
            ExecutionContext(
                request_id="search-stages",
                actor_type="internal_agent",
            ),
        )

        by_id = {item.information_id: item for item in result.items}
        assert "pending" in by_id[first.information_id].scopes
        assert "archived" in by_id[first.information_id].scopes
        assert "cards" in by_id[second.information_id].scopes
        assert len(by_id) == len(result.items)
    finally:
        session.close()
