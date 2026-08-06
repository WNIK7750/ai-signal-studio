import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from ai_signal_api.models import CollectionRunModel, RawItemModel, SourceConfigModel
from ai_signal_api.modules.collection.collectors import CollectedItem
from ai_signal_api.modules.collection.service import SourceService
from ai_signal_api.schemas import SourceCreate


def test_collection_run_creates_a_readable_timeline(client: TestClient) -> None:
    response = client.post("/api/collection-runs", json={})

    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "completed"
    assert run["items_collected"] >= 3
    assert run["items_added"] >= 3

    timeline_response = client.get("/api/timeline")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()
    assert timeline["total"] >= 3
    assert timeline["items"][0]["title"]
    assert timeline["items"][0]["summary"]
    assert timeline["items"][0]["priority"] in {
        "important",
        "watch",
        "normal",
    }
    assert timeline["items"][0]["source_name"]


def test_duplicate_items_from_two_sources_are_stored_once(
    client: TestClient,
) -> None:
    duplicate_source = client.post(
        "/api/sources",
        json={
            "name": "OpenAI 镜像源",
            "kind": "demo",
            "config": {"dataset": "openai"},
            "enabled": True,
        },
    )
    assert duplicate_source.status_code == 201

    run_response = client.post("/api/collection-runs", json={})
    assert run_response.status_code == 201

    timeline = client.get("/api/timeline").json()
    urls = [item["canonical_url"] for item in timeline["items"]]
    assert len(urls) == len(set(urls))


def test_timeline_supports_search_and_priority_filter(
    client: TestClient,
) -> None:
    client.post("/api/collection-runs", json={})

    response = client.get(
        "/api/timeline",
        params={"search": "LangGraph", "priority": "important"},
    )

    assert response.status_code == 200
    timeline = response.json()
    assert timeline["total"] == 1
    assert "LangGraph" in timeline["items"][0]["title"]
    assert timeline["items"][0]["priority"] == "important"


def test_sources_can_be_added_disabled_and_listed(client: TestClient) -> None:
    create_response = client.post(
        "/api/sources",
        json={
            "name": "LangChain Releases",
            "kind": "github_releases",
            "config": {"repository": "langchain-ai/langchain"},
            "enabled": True,
        },
    )
    assert create_response.status_code == 201
    source = create_response.json()

    disable_response = client.patch(
        f"/api/sources/{source['id']}",
        json={"enabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False

    sources = client.get("/api/sources").json()
    assert any(item["name"] == "LangChain Releases" for item in sources)


@pytest.mark.parametrize(
    ("kind", "valid_config", "invalid_config", "error_code"),
    [
        (
            "rss",
            {"url": "https://example.com/feed.xml"},
            {},
            "SOURCE_CONFIG_URL_REQUIRED",
        ),
        (
            "github_releases",
            {"repository": "openai/openai-python"},
            {"url": "https://example.com/releases.xml"},
            "SOURCE_CONFIG_REPOSITORY_REQUIRED",
        ),
        (
            "rss",
            {"url": "https://example.com/feed.xml"},
            None,
            "SOURCE_CONFIG_REQUIRED",
        ),
    ],
)
def test_source_patch_rejects_invalid_complete_definition_and_preserves_data(
    client: TestClient,
    kind: str,
    valid_config: dict[str, str],
    invalid_config: dict[str, str] | None,
    error_code: str,
) -> None:
    created = client.post(
        "/api/sources",
        json={
            "name": f"Patch validation {kind}",
            "kind": kind,
            "config": valid_config,
            "enabled": True,
        },
    ).json()

    response = client.patch(
        f"/api/sources/{created['id']}",
        json={"config": invalid_config},
    )

    assert response.status_code == 422
    assert error_code in response.text
    saved = next(
        source
        for source in client.get("/api/sources").json()
        if source["id"] == created["id"]
    )
    assert saved["config"] == valid_config


def test_source_patch_rejects_read_only_kind_and_preserves_data(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/sources",
        json={
            "name": "Read only source kind",
            "kind": "rss",
            "config": {"url": "https://example.com/feed.xml"},
            "enabled": True,
        },
    ).json()

    response = client.patch(
        f"/api/sources/{created['id']}",
        json={
            "kind": "github_releases",
            "config": {"repository": "openai/openai-python"},
        },
    )

    assert response.status_code == 422
    saved = next(
        source
        for source in client.get("/api/sources").json()
        if source["id"] == created["id"]
    )
    assert saved["kind"] == "rss"
    assert saved["config"] == {"url": "https://example.com/feed.xml"}


def test_source_patch_duplicate_name_returns_conflict_and_preserves_name(
    client: TestClient,
) -> None:
    first = client.post(
        "/api/sources",
        json={
            "name": "First unique source",
            "kind": "rss",
            "config": {"url": "https://example.com/first.xml"},
            "enabled": True,
        },
    ).json()
    second = client.post(
        "/api/sources",
        json={
            "name": "Second unique source",
            "kind": "rss",
            "config": {"url": "https://example.com/second.xml"},
            "enabled": True,
        },
    ).json()

    response = client.patch(
        f"/api/sources/{first['id']}",
        json={"name": second["name"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "SOURCE_NAME_EXISTS"
    saved = next(
        source
        for source in client.get("/api/sources").json()
        if source["id"] == first["id"]
    )
    assert saved["name"] == "First unique source"


def test_source_service_validates_create_without_router(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as session:
        service = SourceService(session)

        with pytest.raises(ValueError, match="SOURCE_CONFIG_URL_REQUIRED"):
            service.create(
                name="Invalid direct source",
                kind="rss",
                config={},
                enabled=True,
            )

        assert all(
            source.name != "Invalid direct source"
            for source in service.list()
        )


def test_timeline_cursor_is_stable_when_items_share_a_timestamp(
    client: TestClient,
) -> None:
    client.post("/api/collection-runs", json={})
    with client.app.state.session_factory() as session:
        shared_timestamp = session.scalar(
            select(RawItemModel.published_at).limit(1)
        )
        session.execute(
            update(RawItemModel).values(published_at=shared_timestamp)
        )
        session.commit()

    seen_ids: list[str] = []
    cursor = None
    while True:
        response = client.get(
            "/api/timeline",
            params={"limit": 1, **({"cursor": cursor} if cursor else {})},
        )
        assert response.status_code == 200
        page = response.json()
        seen_ids.extend(item["id"] for item in page["items"])
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]

    assert len(seen_ids) >= 3
    assert len(seen_ids) == len(set(seen_ids))


def test_source_definition_can_be_tested_without_persisting_it(
    client: TestClient,
) -> None:
    with client.app.state.session_factory() as session:
        sources_before = session.scalar(select(func.count(SourceConfigModel.id)))
        runs_before = session.scalar(select(func.count(CollectionRunModel.id)))

    response = client.post(
        "/api/sources/test-definition",
        json={
            "name": "Draft source",
            "kind": "demo",
            "config": {"dataset": "langgraph"},
            "enabled": True,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "source_id": None,
        "status": "healthy",
        "items_count": 1,
        "sample_titles": ["LangGraph 增强持久化与恢复机制"],
        "error_code": None,
    }
    with client.app.state.session_factory() as session:
        assert session.scalar(select(func.count(SourceConfigModel.id))) == sources_before
        assert session.scalar(select(func.count(CollectionRunModel.id))) == runs_before


class _EmptyCollector:
    def collect(self, config: dict) -> list[CollectedItem]:
        del config
        return []


class _TimeoutCollector:
    def collect(self, config: dict) -> list[CollectedItem]:
        del config
        raise TimeoutError


class _FakeCollectors:
    def __init__(self, collector: object) -> None:
        self.collector = collector

    def resolve(self, kind: str) -> object:
        del kind
        return self.collector


@pytest.mark.parametrize(
    ("collector", "error_code"),
    [
        (_EmptyCollector(), "SOURCE_EMPTY"),
        (_TimeoutCollector(), "SOURCE_TIMEOUT"),
    ],
)
def test_source_definition_test_uses_stable_error_codes(
    client: TestClient,
    collector: object,
    error_code: str,
) -> None:
    with client.app.state.session_factory() as session:
        result = SourceService(
            session,
            collectors=_FakeCollectors(collector),
        ).test_definition(
            SourceCreate(
                name="Draft",
                kind="demo",
                config={},
                enabled=True,
            )
        )

    assert result["status"] == "error"
    assert result["error_code"] == error_code
