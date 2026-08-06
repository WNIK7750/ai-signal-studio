from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.models import RawItemModel
from ai_signal_api.modules.intelligence.agent.schemas import ResearchInput
from ai_signal_api.schemas import ExecutionContext


def _executor_with_information(client):
    client.post(
        "/api/collection-runs",
        json={"source_ids": [], "trigger_type": "test"},
    )
    session = client.app.state.session_factory()
    return (
        session,
        build_capability_executor(session, client.app.state.settings),
    )


def test_research_recommend_never_fabricates_to_requested_limit(client) -> None:
    session, executor = _executor_with_information(client)
    try:
        result = executor.execute(
            "research.recommend",
            ResearchInput(topic="Agent", limit=10, lookback_days=30),
            ExecutionContext(
                request_id="research-recommend",
                actor_type="internal_agent",
            ),
        )
        assert 1 <= len(result.items) <= 3
        assert all(item.information_ids for item in result.items)
        assert all(item.app_path.startswith("/timeline?focus=") for item in result.items)
    finally:
        session.close()


def test_research_match_requirements_marks_unknown_instead_of_guessing(
    client,
) -> None:
    session, executor = _executor_with_information(client)
    try:
        result = executor.execute(
            "research.match_requirements",
            ResearchInput(
                requirements=["开源", "Windows", "官方证据"],
                limit=5,
            ),
            ExecutionContext(
                request_id="research-match",
                actor_type="internal_agent",
            ),
        )
        assert result.items
        assert {
            decision
            for item in result.items
            for decision in item.requirement_decisions.values()
        } <= {"matched", "unknown", "rejected"}
        assert any(
            decision == "unknown"
            for item in result.items
            for decision in item.requirement_decisions.values()
        )
    finally:
        session.close()


def test_research_compare_every_fact_has_information_reference(client) -> None:
    session, executor = _executor_with_information(client)
    try:
        result = executor.execute(
            "research.compare",
            ResearchInput(
                compare_terms=["OpenAI", "LangGraph", "WhisperLive"],
                limit=5,
            ),
            ExecutionContext(
                request_id="research-compare",
                actor_type="internal_agent",
            ),
        )
        assert len(result.comparison) == 3
        assert all(
            fact.information_ids
            for row in result.comparison
            for fact in row.facts
        )
    finally:
        session.close()


def test_trend_brief_includes_representatives_counterexample_and_gaps(
    client,
) -> None:
    session, executor = _executor_with_information(client)
    try:
        result = executor.execute(
            "research.trend_brief",
            ResearchInput(topic="Agent", lookback_days=30, limit=5),
            ExecutionContext(
                request_id="research-trend",
                actor_type="internal_agent",
            ),
        )
        assert result.trends
        assert result.trends[0].information_ids
        assert result.counterexamples
        assert result.coverage_gaps
    finally:
        session.close()


def test_research_backfills_empty_exact_window_from_saved_recent_evidence(
    client,
) -> None:
    session, executor = _executor_with_information(client)
    try:
        session.execute(
            update(RawItemModel).values(
                published_at=(
                    datetime.now(timezone.utc) - timedelta(hours=48)
                )
            )
        )
        session.commit()
        result = executor.execute(
            "research.recommend",
            ResearchInput(
                topic="AI",
                lookback_hours=24,
                fallback_lookback_hours=72,
                allow_workspace_backfill=True,
                limit=3,
            ),
            ExecutionContext(
                request_id="research-backfill",
                actor_type="internal_agent",
            ),
        )

        assert len(result.items) == 3
        assert result.requested_item_count == 0
        assert result.effective_lookback_hours == 72
        assert len(result.backfilled_information_ids) == 3
    finally:
        session.close()
