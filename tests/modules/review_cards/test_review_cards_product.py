from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.capabilities.registry import build_capability_executor
from ai_signal_api.main import create_app
from ai_signal_api.schemas import (
    CardRenderCapabilityInput,
    CardUpdateCapabilityInput,
    ExecutionContext,
)


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


def test_poster_graph_supports_edit_approval_and_idempotent_png_render(
    client: TestClient,
) -> None:
    batch = _collect_and_open_review(client)
    client.post(
        f"/api/review-batches/{batch['id']}/decisions",
        json={
            "decisions": [
                {
                    "item_id": item["id"],
                    "decision": "keep" if index < 2 else "reject",
                }
                for index, item in enumerate(batch["items"])
            ],
            "confirm": True,
        },
    )

    started = client.post(
        "/api/cards/workflows",
        json={"max_chars": 400},
    ).json()
    assert started["status"] == "waiting_approval"
    assert started["interrupt"]["phase"] == "confirm_draft_generation"

    drafts = client.post(
        f"/api/cards/workflows/{started['thread_id']}/resume",
        json={"approved": True},
    ).json()
    assert drafts["status"] == "waiting_approval"
    assert drafts["interrupt"]["phase"] == "confirm_render"
    card_id = drafts["card_ids"][0]
    card = client.get(f"/api/cards/{card_id}").json()

    updated = client.patch(
        f"/api/cards/{card_id}",
        json={
            "expected_revision": card["revision"],
            "title": f"{card['title']}（已编辑）",
            "summary": "这是一段经过人工编辑并确认的卡片摘要。" * 8,
            "key_points": ["保留真实来源", "渲染前显式确认"],
            "template_id": "offline-grid",
            "cover_source": "offline",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == card["revision"] + 1
    stale = client.patch(
        f"/api/cards/{card_id}",
        json={
            "expected_revision": card["revision"],
            "title": card["title"],
            "summary": "这是一段长度满足要求但使用过期版本号的摘要。" * 8,
            "key_points": ["冲突"],
            "template_id": "offline-quote",
            "cover_source": "offline",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == "CARD_REVISION_CONFLICT"

    rendered = client.post(
        f"/api/cards/workflows/{started['thread_id']}/resume",
        json={"approved": True},
    ).json()
    assert rendered["status"] == "completed"
    assert len(rendered["rendered_artifact_ids"]) == 2


def test_workspace_agent_capabilities_can_edit_and_render_cards(
    client: TestClient,
) -> None:
    batch = _collect_and_open_review(client)
    client.post(
        f"/api/review-batches/{batch['id']}/decisions",
        json={
            "decisions": [
                {"item_id": batch["items"][0]["id"], "decision": "keep"}
            ],
            "default_decision": "reject",
            "confirm": True,
        },
    )
    card_id = client.post("/api/cards/generate", json={}).json()["card_ids"][0]

    with client.app.state.session_factory() as session:
        executor = build_capability_executor(
            session,
            client.app.state.settings,
        )
        card = client.get(f"/api/cards/{card_id}").json()
        context = ExecutionContext(
            request_id="req_poster_agent",
            actor_type="internal_agent",
        )
        updated = executor.execute(
            "poster.card.update",
            CardUpdateCapabilityInput(
                card_id=card_id,
                expected_revision=card["revision"],
                title=f"{card['title']}（Agent 编辑）",
                summary="Agent 通过统一能力接口完成卡片编辑并保留真实来源。" * 8,
                key_points=["统一能力", "显式渲染"],
                template_id="offline-grid",
                cover_source="offline",
            ),
            context,
        )
        rendered = executor.execute(
            "poster.card.render",
            CardRenderCapabilityInput(card_id=card_id),
            context.model_copy(
                update={"request_id": "req_poster_render"}
            ),
        )

    assert updated.title.endswith("（Agent 编辑）")
    assert rendered.artifact_id.startswith("artifact_")
    first_render = client.post(f"/api/cards/{card_id}/render").json()
    second_render = client.post(f"/api/cards/{card_id}/render").json()
    assert first_render["artifact_id"] == second_render["artifact_id"]
    content = client.get(
        f"/api/artifacts/{first_render['artifact_id']}/content"
    )
    assert content.status_code == 200
    assert content.content.startswith(b"\x89PNG\r\n\x1a\n")


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
