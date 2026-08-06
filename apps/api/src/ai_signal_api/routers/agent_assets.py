from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_signal_api.dependencies import get_session
from ai_signal_api.models import (
    AgentPackVersionModel,
    ArtifactModel,
    TranscriptionSessionModel,
)
from ai_signal_api.modules.agent_assets.agent_packs import (
    AgentPackError,
    AgentPackService,
)
from ai_signal_api.modules.agent_assets.artifacts import (
    ArtifactError,
    ArtifactService,
)
from ai_signal_api.modules.agent_assets.transcription import (
    FakeRealtimeTranscriptionProvider,
    TranscriptionService,
)


router = APIRouter(tags=["agent-assets"])


class AgentPackImport(BaseModel):
    zip_base64: str = Field(min_length=1)
    activate: bool = True


class AgentPackExport(BaseModel):
    selected_paths: list[str] = Field(default_factory=list, max_length=200)


class AgentPackEdit(BaseModel):
    path: str = Field(min_length=1, max_length=300)
    content: str = Field(max_length=500_000)
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")


class AgentPackRead(BaseModel):
    id: str
    pack_id: str
    version: str
    content_digest: str
    status: str
    previous_version_id: str | None
    validation_result: dict
    created_at: datetime
    activated_at: datetime | None


class ArtifactCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=160)
    content_base64: str = Field(min_length=1)


class ArtifactRead(BaseModel):
    artifact_id: str
    media_type: str
    filename: str
    storage_uri: str
    sha256: str
    size_bytes: int
    status: str
    extracted_text: str
    metadata: dict
    created_at: datetime


class TranscriptionStart(BaseModel):
    language: str = Field(default="zh", min_length=2, max_length=24)
    format: Literal["webm_opus", "pcm_s16le"] = "webm_opus"
    sample_rate: int = Field(default=48000, ge=8000, le=96000)


class TranscriptionRead(BaseModel):
    session_id: str
    status: str
    provider: str
    language: str
    format: str
    sample_rate: int
    final_text: str
    error_code: str | None
    created_at: datetime
    closed_at: datetime | None
    websocket_url: str | None = None
    token: str | None = None


def _pack_read(model: AgentPackVersionModel) -> AgentPackRead:
    return AgentPackRead(
        id=model.id,
        pack_id=model.pack_id,
        version=model.version,
        content_digest=model.content_digest,
        status=model.status,
        previous_version_id=model.previous_version_id,
        validation_result=model.validation_result,
        created_at=model.created_at,
        activated_at=model.activated_at,
    )


def _artifact_read(model: ArtifactModel) -> ArtifactRead:
    return ArtifactRead(
        artifact_id=model.id,
        media_type=model.media_type,
        filename=model.filename,
        storage_uri=model.storage_uri,
        sha256=model.sha256,
        size_bytes=model.size_bytes,
        status=model.status,
        extracted_text=model.extracted_text,
        metadata=model.metadata_json,
        created_at=model.created_at,
    )


def _transcription_read(
    model: TranscriptionSessionModel,
    *,
    token: str | None = None,
) -> TranscriptionRead:
    return TranscriptionRead(
        session_id=model.id,
        status=model.status,
        provider=model.provider,
        language=model.language,
        format=model.audio_format,
        sample_rate=model.sample_rate,
        final_text=model.final_text,
        error_code=model.error_code,
        created_at=model.created_at,
        closed_at=model.closed_at,
        websocket_url=(
            f"/ws/transcription/{model.id}" if token is not None else None
        ),
        token=token,
    )


@router.post(
    "/api/agent-packs/import",
    response_model=AgentPackRead,
    status_code=status.HTTP_201_CREATED,
)
def import_agent_pack(
    payload: AgentPackImport,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentPackRead:
    try:
        model = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).import_base64(
            payload.zip_base64,
            activate=payload.activate,
        )
    except AgentPackError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _pack_read(model)


@router.post("/api/agent-packs/import-preview")
def preview_agent_pack(
    payload: AgentPackImport,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    try:
        return AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).preview_base64(payload.zip_base64)
    except AgentPackError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get(
    "/api/agent-packs/{pack_id}",
    response_model=AgentPackRead,
)
def get_agent_pack(
    pack_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentPackRead:
    try:
        model = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).get_active(pack_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _pack_read(model)


@router.get(
    "/api/agent-packs/{pack_id}/versions",
    response_model=list[AgentPackRead],
)
def list_agent_pack_versions(
    pack_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> list[AgentPackRead]:
    return [
        _pack_read(model)
        for model in AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).list_versions(pack_id)
    ]


@router.post(
    "/api/agent-packs/versions/{version_id}/activate",
    response_model=AgentPackRead,
)
def activate_agent_pack_version(
    version_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentPackRead:
    try:
        model = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).activate_version(version_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _pack_read(model)


@router.post(
    "/api/agent-packs/{pack_id}/edit",
    response_model=AgentPackRead,
)
def edit_agent_pack(
    pack_id: str,
    payload: AgentPackEdit,
    request: Request,
    session: Session = Depends(get_session),
) -> AgentPackRead:
    try:
        model = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).edit_file(
            pack_id,
            path=payload.path,
            content=payload.content,
            version=payload.version,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AgentPackError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _pack_read(model)


@router.post("/api/agent-packs/{pack_id}/export")
def export_agent_pack(
    pack_id: str,
    payload: AgentPackExport,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    try:
        content = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).export_base64(
            pack_id,
            payload.selected_paths or None,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except AgentPackError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "filename": f"{pack_id}.zip",
        "content_base64": content,
    }


@router.get("/api/agent-packs/{pack_id}/search")
def search_agent_pack(
    pack_id: str,
    request: Request,
    q: str = "",
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if not q.strip():
        return {"matches": []}
    try:
        matches = AgentPackService(
            session,
            request.app.state.settings.agent_pack_root,
        ).search(pack_id, q.strip())
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {"matches": matches}


@router.post(
    "/api/artifacts",
    response_model=ArtifactRead,
    status_code=status.HTTP_201_CREATED,
)
def create_artifact(
    payload: ArtifactCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> ArtifactRead:
    try:
        artifact = ArtifactService(
            session,
            request.app.state.settings.artifact_root,
            request.app.state.settings.artifact_max_bytes,
        ).create(**payload.model_dump())
    except ArtifactError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _artifact_read(artifact)


@router.get("/api/artifacts", response_model=list[ArtifactRead])
def list_artifacts(
    request: Request,
    session: Session = Depends(get_session),
) -> list[ArtifactRead]:
    return [
        _artifact_read(artifact)
        for artifact in ArtifactService(
            session,
            request.app.state.settings.artifact_root,
            request.app.state.settings.artifact_max_bytes,
        ).list()
    ]


@router.get("/api/artifacts/{artifact_id}", response_model=ArtifactRead)
def get_artifact(
    artifact_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ArtifactRead:
    try:
        artifact = ArtifactService(
            session,
            request.app.state.settings.artifact_root,
            request.app.state.settings.artifact_max_bytes,
        ).get(artifact_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _artifact_read(artifact)


@router.get("/api/artifacts/{artifact_id}/content")
def get_artifact_content(
    artifact_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> FileResponse:
    try:
        artifact = ArtifactService(
            session,
            request.app.state.settings.artifact_root,
            request.app.state.settings.artifact_max_bytes,
        ).get(artifact_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return FileResponse(
        artifact.storage_uri,
        media_type=artifact.media_type,
        filename=artifact.filename,
    )


@router.delete("/api/artifacts/{artifact_id}", response_model=ArtifactRead)
def archive_artifact(
    artifact_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> ArtifactRead:
    try:
        artifact = ArtifactService(
            session,
            request.app.state.settings.artifact_root,
            request.app.state.settings.artifact_max_bytes,
        ).archive(artifact_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _artifact_read(artifact)


@router.post(
    "/api/transcription/sessions",
    response_model=TranscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def start_transcription(
    payload: TranscriptionStart,
    request: Request,
    session: Session = Depends(get_session),
) -> TranscriptionRead:
    model, token = TranscriptionService(
        session,
        request.app.state.settings.stt_token_ttl_seconds,
    ).create(
        language=payload.language,
        audio_format=payload.format,
        sample_rate=payload.sample_rate,
    )
    return _transcription_read(model, token=token)


@router.get(
    "/api/transcription/sessions/{session_id}",
    response_model=TranscriptionRead,
)
def get_transcription(
    session_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> TranscriptionRead:
    try:
        model = TranscriptionService(
            session,
            request.app.state.settings.stt_token_ttl_seconds,
        ).get(session_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _transcription_read(model)


@router.websocket("/ws/transcription/{session_id}")
async def transcription_socket(
    websocket: WebSocket,
    session_id: str,
    token: str = "",
) -> None:
    await websocket.accept()
    settings = websocket.app.state.settings
    with websocket.app.state.session_factory() as session:
        service = TranscriptionService(
            session,
            settings.stt_token_ttl_seconds,
        )
        try:
            model = service.get(session_id)
        except LookupError:
            await websocket.send_json(
                {
                    "type": "session.error",
                    "code": "STT_SESSION_NOT_FOUND",
                    "message": "Transcription session not found.",
                    "retryable": False,
                }
            )
            await websocket.close(code=4404)
            return
        if not service.authorize(model, token):
            await websocket.send_json(
                {
                    "type": "session.error",
                    "code": "STT_TOKEN_INVALID",
                    "message": "Transcription token is invalid or expired.",
                    "retryable": False,
                }
            )
            await websocket.close(code=4401)
            return
        provider = getattr(
            websocket.app.state,
            "transcription_provider",
            FakeRealtimeTranscriptionProvider(),
        )
        provider_session = None
        try:
            while True:
                message = await websocket.receive()
                if message.get("text") is not None:
                    try:
                        control = websocket.app.state.json_loads(
                            message["text"]
                        )
                    except (TypeError, ValueError):
                        await websocket.send_json(
                            {
                                "type": "session.error",
                                "code": "STT_MESSAGE_INVALID",
                                "message": "Invalid JSON control message.",
                                "retryable": False,
                            }
                        )
                        continue
                    message_type = control.get("type")
                    if message_type == "start":
                        if provider_session is not None:
                            await websocket.send_json(
                                {
                                    "type": "session.warning",
                                    "code": "STT_ALREADY_STARTED",
                                    "message": "Session is already streaming.",
                                }
                            )
                            continue
                        provider_session = await provider.open(control)
                        service.update(model, status="streaming")
                        await websocket.send_json(
                            {
                                "type": "session.started",
                                "session_id": model.id,
                                "provider": model.provider,
                            }
                        )
                    elif message_type == "pause":
                        service.update(model, status="paused")
                    elif message_type == "resume":
                        service.update(model, status="streaming")
                    elif message_type == "stop":
                        if provider_session is None:
                            raise ValueError("STT_NOT_STARTED")
                        summary = await provider.close(provider_session)
                        final_text = str(summary.get("final_text", ""))
                        service.update(
                            model,
                            status="closed",
                            final_text=final_text,
                        )
                        await websocket.send_json(
                            {
                                "type": "session.closed",
                                "session_id": model.id,
                                "final_text": final_text,
                            }
                        )
                        await websocket.close(code=1000)
                        return
                    else:
                        raise ValueError("STT_STATE_INVALID")
                elif message.get("bytes") is not None:
                    chunk = message["bytes"]
                    if provider_session is None or model.status != "streaming":
                        raise ValueError("STT_NOT_STREAMING")
                    if len(chunk) > settings.stt_max_chunk_bytes:
                        raise ValueError("STT_CHUNK_TOO_LARGE")
                    for event in await provider.push_audio(
                        provider_session,
                        chunk,
                    ):
                        payload = {
                            **event,
                            "session_id": model.id,
                        }
                        if event["type"] == "transcript.final":
                            service.update(
                                model,
                                status="streaming",
                                final_text=str(event["text"]),
                            )
                        await websocket.send_json(payload)
        except WebSocketDisconnect:
            if model.status not in {"closed", "error"}:
                service.update(
                    model,
                    status="interrupted",
                    final_text=(
                        provider_session.final_text
                        if provider_session is not None
                        else model.final_text
                    ),
                )
        except Exception as error:
            code = str(error)
            if not code.startswith("STT_"):
                code = "STT_PROVIDER_ERROR"
            service.update(model, status="error", error_code=code)
            await websocket.send_json(
                {
                    "type": "session.error",
                    "code": code,
                    "message": "Realtime transcription failed.",
                    "retryable": code == "STT_PROVIDER_ERROR",
                }
            )
            await websocket.close(code=1011)
