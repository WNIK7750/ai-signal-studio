from fastapi.testclient import TestClient


def test_information_state_can_be_saved_and_filtered(
    client: TestClient,
) -> None:
    client.post("/api/collection-runs", json={})
    item = client.get("/api/timeline").json()["items"][0]

    update = client.patch(
        f"/api/information/{item['id']}/state",
        json={
            "seen": True,
            "starred": True,
            "archived": False,
            "note": "后续用于 Agent 工作流研究",
        },
    )

    assert update.status_code == 200
    assert update.json()["seen"] is True
    assert update.json()["starred"] is True
    assert update.json()["note"] == "后续用于 Agent 工作流研究"

    starred = client.get("/api/timeline", params={"starred": True}).json()
    assert starred["total"] == 1
    assert starred["items"][0]["id"] == item["id"]
    assert starred["items"][0]["seen"] is True


def test_saved_view_preserves_query_and_display(client: TestClient) -> None:
    create = client.post(
        "/api/saved-views",
        json={
            "name": "重要且未查看",
            "query": {"priority": "important", "seen": False},
            "display": {"layout": "compact", "sort": "newest"},
            "pinned": True,
            "is_default": False,
        },
    )

    assert create.status_code == 201
    saved = create.json()
    assert saved["query"]["seen"] is False

    update = client.patch(
        f"/api/saved-views/{saved['id']}",
        json={"is_default": True},
    )
    assert update.status_code == 200
    assert update.json()["is_default"] is True

    listed = client.get("/api/saved-views").json()
    assert [item["name"] for item in listed] == ["重要且未查看"]
