"""Optional WhisperLive boundary adapter.

The product imports only this stable adapter surface. A concrete WebSocket
transport is supplied by the manual integration launcher so ordinary tests do
not import or start WhisperLive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class WhisperLiveTransport(Protocol):
    async def open(self, config: dict[str, object]) -> str: ...
    async def send_audio(
        self,
        vendor_session_id: str,
        chunk: bytes,
    ) -> list[dict[str, object]]: ...
    async def close(self, vendor_session_id: str) -> None: ...


@dataclass(slots=True)
class WhisperLiveSession:
    vendor_session_id: str
    final_text: str = ""
    revisions: dict[str, int] = field(default_factory=dict)


class WhisperLiveAdapter:
    def __init__(self, transport: WhisperLiveTransport) -> None:
        self.transport = transport

    async def open(
        self,
        config: dict[str, object],
    ) -> WhisperLiveSession:
        return WhisperLiveSession(
            vendor_session_id=await self.transport.open(config)
        )

    async def push_audio(
        self,
        session: WhisperLiveSession,
        chunk: bytes,
    ) -> list[dict[str, object]]:
        if not chunk:
            raise ValueError("STT_AUDIO_CHUNK_EMPTY")
        raw_events = await self.transport.send_audio(
            session.vendor_session_id,
            chunk,
        )
        return [
            self._normalize(session, event)
            for event in raw_events
            if event.get("type") in {"partial", "final", "warning"}
        ]

    async def close(
        self,
        session: WhisperLiveSession,
    ) -> dict[str, object]:
        await self.transport.close(session.vendor_session_id)
        return {"final_text": session.final_text}

    @staticmethod
    def _normalize(
        session: WhisperLiveSession,
        event: dict[str, object],
    ) -> dict[str, object]:
        vendor_type = str(event["type"])
        if vendor_type == "warning":
            return {
                "type": "warning",
                "code": "STT_PROVIDER_WARNING",
                "message": "实时转写服务报告可恢复警告。",
            }
        segment_id = str(event.get("segment_id") or "segment")
        revision = session.revisions.get(segment_id, 0) + 1
        session.revisions[segment_id] = revision
        text = str(event.get("text") or "")
        normalized = {
            "type": f"transcript.{vendor_type}",
            "segment_id": segment_id,
            "revision": revision,
            "text": text,
            "start_ms": int(event.get("start_ms") or 0),
            "end_ms": int(event.get("end_ms") or 0),
        }
        if vendor_type == "final":
            session.final_text = (
                f"{session.final_text} {text}".strip()
            )
        return normalized
