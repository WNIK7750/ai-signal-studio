from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.main import create_app


def _collect_and_open_review(client: TestClient) -> dict:
    collection = client.post("/api/collection-runs", json={})
    assert collection.status_code == 201

    response = client.get("/api/review-batches/current")
    assert response.status_code == 200
    batch = response.json()
    assert len(batch["items"]) >= 3
    return batch


def test_collection_items_can_be_reviewed_without_deleting_rejections(
    client: TestClient,
) -> None:
    batch = _collect_and_open_review(client)
    item_ids = [item["id"] for item in batch["items"]]
    decisions = [
        {"item_id": item_ids[0], "decision": "keep"},
        {"item_id": item_ids[1], "decision": "reject"},
        {"item_id": item_ids[2], "decision": "defer"},
    ]

    response = client.post(
        f"/api/review-batches/{batch['id']}/decisions",
        json={"decisions": decisions, "confirm": True},
    )

    assert response.status_code == 200
    completed = response.json()
    assert completed["status"] == "completed"
    assert {item["decision"] for item in completed["items"]} >= {
        "keep",
        "reject",
        "defer",
    }

    timeline = client.get("/api/timeline").json()
    assert timeline["total"] >= 3
    assert client.get("/api/review-batches/current").json()["id"] == batch["id"]


def test_cards_are_generated_only_from_kept_items_and_are_idempotent(
    client: TestClient,
) -> None:
    batch = _collect_and_open_review(client)
    decisions = [
        {
            "item_id": item["id"],
            "decision": "keep" if index < 2 else "reject",
        }
        for index, item in enumerate(batch["items"])
    ]
    client.post(
        f"/api/review-batches/{batch['id']}/decisions",
        json={"decisions": decisions, "confirm": True},
    )

    first = client.post("/api/cards/generate", json={})
    second = client.post("/api/cards/generate", json={})

    assert first.status_code == 201
    assert first.json()["created"] == 2
    assert second.status_code == 201
    assert second.json()["created"] == 0

    cards = client.get("/api/cards").json()
    assert cards["total"] == 2
    card = cards["items"][0]
    assert 0 <= card["cover_variant"] <= 5
    assert card["source_name"]
    assert card["published_at"]

    detail = client.get(f"/api/cards/{card['id']}")
    assert detail.status_code == 200
    assert detail.json()["canonical_url"].startswith("https://")
    assert detail.json()["key_points"]


def test_card_feed_supports_date_and_left_rail_filters(
    client: TestClient,
) -> None:
    batch = _collect_and_open_review(client)
    client.post(
        f"/api/review-batches/{batch['id']}/decisions",
        json={
            "decisions": [
                {"item_id": item["id"], "decision": "keep"}
                for item in batch["items"]
            ],
            "confirm": True,
        },
    )
    client.post("/api/cards/generate", json={})
    first_card = client.get("/api/cards").json()["items"][0]
    day = first_card["published_at"][:10]

    response = client.get(
        "/api/cards",
        params={
            "day": day,
            "priority": first_card["priority"],
            "topic": first_card["topics"][0],
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert all(
        item["published_at"].startswith(day)
        for item in response.json()["items"]
    )


def test_agent_uses_the_same_review_and_card_capabilities(
    client: TestClient,
) -> None:
    _collect_and_open_review(client)

    review = client.post(
        "/api/agent-runs",
        json={"message": "保留全部待审核信息并确认"},
    )
    assert review.status_code == 200
    assert review.json()["capability_calls"][0]["capability_id"] == (
        "review.batch.submit"
    )

    cards = client.post(
        "/api/agent-runs",
        json={"message": "为已保留的信息生成卡片"},
    )
    assert cards.status_code == 200
    assert cards.json()["capability_calls"][0]["capability_id"] == (
        "poster.draft.generate"
    )
    assert client.get("/api/cards").json()["total"] >= 3


def test_capability_switch_blocks_every_entry_point(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=f"sqlite:///{(tmp_path / 'disabled.db').as_posix()}",
            disabled_capabilities=["review.batch.submit"],
        ),
        seed_demo_sources=True,
    )
    with TestClient(app) as client:
        batch = _collect_and_open_review(client)
        payload = {
            "decisions": [
                {"item_id": item["id"], "decision": "keep"}
                for item in batch["items"]
            ],
            "confirm": True,
        }

        rest = client.post(
            f"/api/review-batches/{batch['id']}/decisions",
            json=payload,
        )
        agent = client.post(
            "/api/agent-runs",
            json={"message": "保留全部待审核信息并确认"},
        )

        assert rest.status_code == 403
        assert rest.json()["detail"] == "CAPABILITY_DISABLED"
        assert agent.status_code == 403
