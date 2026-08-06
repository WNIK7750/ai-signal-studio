from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from ai_signal_api.modules.agent_assets.agent_packs import AgentPackService


def _pack_zip(*, version: str = "1.0.0", unsafe: bool = False) -> str:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr(
            "agent.yaml",
            "\n".join(
                [
                    "id: ai-editor",
                    "name: AI Editor",
                    f"version: {version}",
                    "entrypoints:",
                    "  system: system.md",
                    "  behavior: behavior.md",
                    "capability_config: capabilities.yaml",
                    "memory_paths:",
                    "  - memory/preferences.md",
                ]
            ),
        )
        archive.writestr("system.md", "只引用可追溯证据。")
        archive.writestr("behavior.md", "遇到未知信息时明确说明。")
        archive.writestr("capabilities.yaml", "enabled: []")
        archive.writestr(
            "memory/preferences.md",
            "用户确认偏好：优先使用官方来源。",
        )
        if unsafe:
            archive.writestr("../escape.txt", "must not escape")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_agent_pack_import_is_atomic_and_searchable(
    client: TestClient,
) -> None:
    imported = client.post(
        "/api/agent-packs/import",
        json={"zip_base64": _pack_zip(), "activate": True},
    )
    assert imported.status_code == 201
    active = imported.json()
    assert active["pack_id"] == "ai-editor"
    assert active["status"] == "active"

    rejected = client.post(
        "/api/agent-packs/import",
        json={"zip_base64": _pack_zip(version="2.0.0", unsafe=True)},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == "AGENT_PACK_PATH_UNSAFE"

    current = client.get("/api/agent-packs/ai-editor").json()
    assert current["version"] == "1.0.0"
    search = client.get(
        "/api/agent-packs/ai-editor/search",
        params={"q": "官方来源"},
    ).json()
    assert search["matches"][0]["path"] == "memory/preferences.md"

    preview = client.post(
        "/api/agent-packs/import-preview",
        json={"zip_base64": _pack_zip(version="2.0.0")},
    ).json()
    assert preview["version"] == "2.0.0"
    assert "agent.yaml" in preview["changed"]

    edited = client.post(
        "/api/agent-packs/ai-editor/edit",
        json={
            "path": "memory/preferences.md",
            "content": "用户确认偏好：只看可验证事实。",
            "version": "1.1.0",
        },
    ).json()
    assert edited["status"] == "active"
    assert edited["version"] == "1.1.0"
    versions = client.get(
        "/api/agent-packs/ai-editor/versions"
    ).json()
    original = next(item for item in versions if item["version"] == "1.0.0")
    restored = client.post(
        f"/api/agent-packs/versions/{original['id']}/activate"
    ).json()
    assert restored["status"] == "active"

    exported = client.post(
        "/api/agent-packs/ai-editor/export",
        json={"selected_paths": ["memory/preferences.md"]},
    ).json()
    with ZipFile(
        BytesIO(base64.b64decode(exported["content_base64"]))
    ) as archive:
        assert sorted(archive.namelist()) == [
            "agent.yaml",
            "memory/preferences.md",
        ]


def test_agent_pack_import_preserves_a_conflicting_immutable_directory(
    client: TestClient,
    tmp_path: Path,
) -> None:
    encoded = _pack_zip(version="9.9.0")
    with ZipFile(BytesIO(base64.b64decode(encoded))) as archive:
        files = {
            item.filename: archive.read(item)
            for item in archive.infolist()
            if not item.is_dir()
        }
    digest = AgentPackService._content_digest(files)
    root = tmp_path / "agent-packs"
    conflicting = root / "ai-editor" / f"9.9.0-{digest[:12]}"
    conflicting.mkdir(parents=True)
    marker = conflicting / "preserve-me.txt"
    marker.write_text("local data must not be overwritten", encoding="utf-8")

    with client.app.state.session_factory() as session:
        imported = AgentPackService(session, root).import_base64(encoded)

    installed = Path(imported.storage_uri)
    assert installed.name == f"9.9.0-{digest}"
    assert AgentPackService._content_digest(
        AgentPackService._read_files(installed)
    ) == digest
    assert marker.read_text(encoding="utf-8") == (
        "local data must not be overwritten"
    )


def test_artifact_upload_deduplicates_and_returns_a_reference(
    client: TestClient,
) -> None:
    content = "# 调研笔记\n\n仅使用官方资料。".encode()
    payload = {
        "filename": "research.md",
        "media_type": "text/markdown",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }

    created = client.post("/api/artifacts", json=payload)
    duplicate = client.post("/api/artifacts", json=payload)

    assert created.status_code == duplicate.status_code == 201
    artifact = created.json()
    assert artifact["artifact_id"] == duplicate.json()["artifact_id"]
    assert artifact["size_bytes"] == len(content)
    assert artifact["sha256"]
    detail = client.get(f"/api/artifacts/{artifact['artifact_id']}").json()
    assert "仅使用官方资料" in detail["extracted_text"]
    assert "content_base64" not in json.dumps(detail)


def test_transcription_websocket_emits_normalized_events_and_closes(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/transcription/sessions",
        json={"language": "zh", "format": "webm_opus", "sample_rate": 48000},
    )
    assert created.status_code == 201
    session = created.json()

    with client.websocket_connect(
        f"/ws/transcription/{session['session_id']}?token={session['token']}"
    ) as websocket:
        websocket.send_json(
            {
                "type": "start",
                "language": "zh",
                "format": "webm_opus",
                "sample_rate": 48000,
            }
        )
        assert websocket.receive_json()["type"] == "session.started"
        websocket.send_bytes(b"deterministic fake audio")
        assert websocket.receive_json()["type"] == "transcript.partial"
        final = websocket.receive_json()
        assert final["type"] == "transcript.final"
        assert final["text"] == "这是确定性的测试转写。"
        websocket.send_json({"type": "stop"})
        closed = websocket.receive_json()
        assert closed["type"] == "session.closed"
        assert closed["final_text"] == final["text"]

    persisted = client.get(
        f"/api/transcription/sessions/{session['session_id']}"
    ).json()
    assert persisted["status"] == "closed"
    assert persisted["final_text"] == "这是确定性的测试转写。"


def test_transcription_websocket_rejects_an_invalid_token(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/transcription/sessions",
        json={"language": "zh", "format": "webm_opus", "sample_rate": 48000},
    ).json()

    with client.websocket_connect(
        f"/ws/transcription/{created['session_id']}?token=invalid"
    ) as websocket:
        message = websocket.receive_json()

    assert message["type"] == "session.error"
    assert message["code"] == "STT_TOKEN_INVALID"


def test_workspace_agent_retrieves_artifacts_through_a_capability(
    client: TestClient,
) -> None:
    content = "这份文档要求优先引用官方资料。".encode()
    artifact = client.post(
        "/api/artifacts",
        json={
            "filename": "evidence.txt",
            "media_type": "text/plain",
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    ).json()
    conversation = client.post("/api/agent-conversations", json={}).json()
    turn = client.post(
        f"/api/agent-conversations/{conversation['id']}/turns",
        json={
            "message": "请在文档附件中查找官方资料",
            "client_message_id": "artifact-agent-search",
        },
    ).json()
    client.get(f"/api/agent-turns/{turn['id']}/events")

    completed = client.get(f"/api/agent-turns/{turn['id']}").json()
    assert completed["status"] == "complete"
    block = next(
        item
        for item in completed["result"]["result_blocks"]
        if item["type"] == "artifact_list"
    )
    assert block["data"]["items"][0]["artifact_id"] == artifact["artifact_id"]
