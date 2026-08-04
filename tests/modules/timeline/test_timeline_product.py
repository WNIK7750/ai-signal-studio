from fastapi.testclient import TestClient


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
