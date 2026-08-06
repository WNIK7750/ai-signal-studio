from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Protocol

from sqlalchemy.orm import Session

from ai_signal_api.models import TranscriptionSessionModel, utc_now


@dataclass(slots=True)
class ProviderSession:
    final_text: str = ""
    revision: int = 0


class RealtimeTranscriptionProvider(Protocol):
    async def open(self, config: dict[str, object]) -> ProviderSession: ...

    async def push_audio(
        self,
        session: ProviderSession,
        chunk: bytes,
    ) -> list[dict[str, object]]: ...

    async def close(
        self,
        session: ProviderSession,
    ) -> dict[str, object]: ...


class FakeRealtimeTranscriptionProvider:
    async def open(self, config: dict[str, object]) -> ProviderSession:
        del config
        return ProviderSession()

    async def push_audio(
        self,
        session: ProviderSession,
        chunk: bytes,
    ) -> list[dict[str, object]]:
        if not chunk:
            raise ValueError("STT_AUDIO_CHUNK_EMPTY")
        session.revision += 2
        session.final_text = "这是确定性的测试转写。"
        return [
            {
                "type": "transcript.partial",
                "segment_id": "segment_1",
                "revision": session.revision - 1,
                "text": "这是确定性的测试",
                "start_ms": 0,
                "end_ms": 800,
            },
            {
                "type": "transcript.final",
                "segment_id": "segment_1",
                "revision": session.revision,
                "text": session.final_text,
                "start_ms": 0,
                "end_ms": 1200,
            },
        ]

    async def close(
        self,
        session: ProviderSession,
    ) -> dict[str, object]:
        return {"final_text": session.final_text}


class TranscriptionService:
    def __init__(self, session: Session, ttl_seconds: int) -> None:
        self.session = session
        self.ttl_seconds = ttl_seconds

    def create(
        self,
        *,
        language: str,
        audio_format: str,
        sample_rate: int,
    ) -> tuple[TranscriptionSessionModel, str]:
        token = secrets.token_urlsafe(32)
        model = TranscriptionSessionModel(
            language=language,
            audio_format=audio_format,
            sample_rate=sample_rate,
            token_digest=self.token_digest(token),
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=self.ttl_seconds),
        )
        self.session.add(model)
        self.session.commit()
        return model, token

    def get(self, session_id: str) -> TranscriptionSessionModel:
        model = self.session.get(TranscriptionSessionModel, session_id)
        if model is None:
            raise LookupError("STT_SESSION_NOT_FOUND")
        return model

    def authorize(self, model: TranscriptionSessionModel, token: str) -> bool:
        expires_at = model.token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return (
            secrets.compare_digest(
                model.token_digest,
                self.token_digest(token),
            )
            and expires_at > datetime.now(timezone.utc)
            and model.status == "created"
        )

    def update(
        self,
        model: TranscriptionSessionModel,
        *,
        status: str,
        final_text: str | None = None,
        error_code: str | None = None,
    ) -> None:
        model.status = status
        if final_text is not None:
            model.final_text = final_text
        model.error_code = error_code
        if status in {"closed", "error", "interrupted"}:
            model.closed_at = utc_now()
        self.session.commit()

    @staticmethod
    def token_digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()
