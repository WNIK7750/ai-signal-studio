from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePath

from sqlalchemy import or_, select
from sqlalchemy.orm import Session
import yaml

from ai_signal_api.models import ArtifactModel, utc_now
from ai_signal_api.modules.agent_assets.schemas import (
    ArtifactSearchMatch,
    ArtifactSearchResult,
)


ALLOWED_MEDIA_TYPES = {
    "text/plain",
    "text/markdown",
    "application/json",
    "application/yaml",
    "text/yaml",
    "image/png",
    "image/jpeg",
    "image/webp",
}


class ArtifactError(ValueError):
    pass


class ArtifactService:
    def __init__(
        self,
        session: Session,
        root: Path,
        max_bytes: int,
    ) -> None:
        self.session = session
        self.root = root.resolve()
        self.max_bytes = max_bytes

    def create(
        self,
        *,
        filename: str,
        media_type: str,
        content_base64: str,
        metadata: dict[str, object] | None = None,
    ) -> ArtifactModel:
        if PurePath(filename).name != filename or not filename.strip():
            raise ArtifactError("ARTIFACT_FILENAME_INVALID")
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ArtifactError("ARTIFACT_MEDIA_TYPE_UNSUPPORTED")
        try:
            content = base64.b64decode(content_base64, validate=True)
        except ValueError as error:
            raise ArtifactError("ARTIFACT_CONTENT_INVALID") from error
        if not content:
            raise ArtifactError("ARTIFACT_EMPTY")
        if len(content) > self.max_bytes:
            raise ArtifactError("ARTIFACT_TOO_LARGE")
        self._validate_magic(media_type, content)
        digest = hashlib.sha256(content).hexdigest()
        existing = self.session.scalar(
            select(ArtifactModel).where(
                ArtifactModel.sha256 == digest,
                ArtifactModel.status == "active",
            )
        )
        if existing is not None:
            return existing
        extracted_text = self._extract_text(media_type, content)
        artifact = ArtifactModel(
            media_type=media_type,
            filename=filename,
            storage_uri="pending",
            sha256=digest,
            size_bytes=len(content),
            extracted_text=extracted_text[:200_000],
            metadata_json={
                "parser": "native-v1",
                "source_title": "本地上传",
                **(metadata or {}),
            },
        )
        self.session.add(artifact)
        self.session.flush()
        now = utc_now()
        destination = (
            self.root
            / artifact.workspace_id
            / f"{now.year:04d}"
            / f"{now.month:02d}"
            / artifact.id
            / filename
        ).resolve()
        if not destination.is_relative_to(self.root):
            raise ArtifactError("ARTIFACT_PATH_UNSAFE")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        artifact.storage_uri = str(destination)
        self.session.commit()
        return artifact

    def get(self, artifact_id: str) -> ArtifactModel:
        artifact = self.session.get(ArtifactModel, artifact_id)
        if artifact is None or artifact.status != "active":
            raise LookupError("ARTIFACT_NOT_FOUND")
        return artifact

    def image_data_url(self, artifact_id: str) -> str:
        """Resolve a validated image handle for a transient model request."""

        artifact = self.get(artifact_id)
        if not artifact.media_type.startswith("image/"):
            raise ArtifactError("ARTIFACT_NOT_IMAGE")
        path = Path(artifact.storage_uri).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            raise ArtifactError("ARTIFACT_PATH_UNSAFE")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != artifact.sha256:
            raise ArtifactError("ARTIFACT_DIGEST_MISMATCH")
        return (
            f"data:{artifact.media_type};base64,"
            f"{base64.b64encode(content).decode('ascii')}"
        )

    def list(self) -> list[ArtifactModel]:
        return list(
            self.session.scalars(
                select(ArtifactModel)
                .where(ArtifactModel.status == "active")
                .order_by(ArtifactModel.created_at.desc())
            )
        )

    def archive(self, artifact_id: str) -> ArtifactModel:
        artifact = self.get(artifact_id)
        artifact.status = "archived"
        artifact.archived_at = utc_now()
        self.session.commit()
        return artifact

    def search(self, query: str, limit: int = 10) -> ArtifactSearchResult:
        pattern = f"%{query.strip()}%"
        models = list(
            self.session.scalars(
                select(ArtifactModel)
                .where(
                    ArtifactModel.status == "active",
                    or_(
                        ArtifactModel.filename.ilike(pattern),
                        ArtifactModel.extracted_text.ilike(pattern),
                    ),
                )
                .order_by(ArtifactModel.created_at.desc())
                .limit(limit)
            )
        )
        return ArtifactSearchResult(
            matches=[
                ArtifactSearchMatch(
                    artifact_id=model.id,
                    filename=model.filename,
                    media_type=model.media_type,
                    excerpt=model.extracted_text[:400],
                )
                for model in models
            ]
        )

    @staticmethod
    def _validate_magic(media_type: str, content: bytes) -> None:
        if media_type == "image/png" and not content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ArtifactError("ARTIFACT_MAGIC_MISMATCH")
        if media_type == "image/jpeg" and not content.startswith(b"\xff\xd8\xff"):
            raise ArtifactError("ARTIFACT_MAGIC_MISMATCH")
        if media_type == "image/webp" and not (
            content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        ):
            raise ArtifactError("ARTIFACT_MAGIC_MISMATCH")

    @staticmethod
    def _extract_text(media_type: str, content: bytes) -> str:
        if media_type.startswith("image/"):
            return ""
        try:
            value = content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ArtifactError("ARTIFACT_TEXT_ENCODING_INVALID") from error
        try:
            if media_type == "application/json":
                json.loads(value)
            elif media_type in {"application/yaml", "text/yaml"}:
                yaml.safe_load(value)
        except (json.JSONDecodeError, yaml.YAMLError) as error:
            raise ArtifactError("ARTIFACT_PARSE_FAILED") from error
        return value
