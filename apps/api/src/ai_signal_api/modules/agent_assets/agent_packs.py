from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
from typing import Any
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from jsonschema import Draft202012Validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session
import yaml

from ai_signal_api.models import AgentPackVersionModel, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[6]
SCHEMA_PATH = PROJECT_ROOT / "contracts/02-agent-pack/agent-pack.schema.json"
MAX_ARCHIVE_BYTES = 10_000_000
MAX_EXPANDED_BYTES = 20_000_000
MAX_FILES = 200


class AgentPackError(ValueError):
    pass


class AgentPackService:
    def __init__(self, session: Session, root: Path) -> None:
        self.session = session
        self.root = root.resolve()

    def import_base64(
        self,
        value: str,
        *,
        activate: bool = True,
        imported_by: str = "local",
    ) -> AgentPackVersionModel:
        try:
            archive_bytes = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise AgentPackError("AGENT_PACK_ARCHIVE_INVALID") from error
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            raise AgentPackError("AGENT_PACK_ARCHIVE_TOO_LARGE")
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".staging-",
            dir=self.root,
        ) as temporary:
            staging = Path(temporary)
            manifest, files = self._validate_and_extract(
                archive_bytes,
                staging,
            )
            digest = self._content_digest(files)
            pack_id = str(manifest["id"])
            version = str(manifest["version"])
            existing = self.session.scalar(
                select(AgentPackVersionModel).where(
                    AgentPackVersionModel.pack_id == pack_id,
                    AgentPackVersionModel.version == version,
                    AgentPackVersionModel.content_digest == digest,
                )
            )
            if existing is not None:
                if activate:
                    self._activate(existing)
                return existing
            previous = self._active(pack_id)
            destination = (
                self.root / pack_id / f"{version}-{digest[:12]}"
            ).resolve()
            if not destination.is_relative_to(self.root):
                raise AgentPackError("AGENT_PACK_PATH_UNSAFE")
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and not self._storage_matches(
                destination,
                digest,
            ):
                destination = (
                    self.root / pack_id / f"{version}-{digest}"
                ).resolve()
                if not destination.is_relative_to(self.root):
                    raise AgentPackError("AGENT_PACK_PATH_UNSAFE")
            if destination.exists():
                if not self._storage_matches(destination, digest):
                    raise AgentPackError("AGENT_PACK_STORAGE_CONFLICT")
            else:
                try:
                    os.replace(staging, destination)
                except (FileExistsError, PermissionError):
                    # Another local process may have installed the same immutable
                    # content between the existence check and the atomic rename.
                    if (
                        not destination.is_dir()
                        or self._content_digest(self._read_files(destination))
                        != digest
                    ):
                        raise AgentPackError(
                            "AGENT_PACK_STORAGE_CONFLICT"
                        ) from None
            model = AgentPackVersionModel(
                pack_id=pack_id,
                version=version,
                content_digest=digest,
                storage_uri=str(destination),
                status="inactive",
                previous_version_id=previous.id if previous else None,
                validation_result={
                    "status": "valid",
                    "files": sorted(files),
                },
                imported_by=imported_by,
            )
            self.session.add(model)
            self.session.flush()
            self._index(model, destination, files)
            if activate:
                self._activate(model)
            else:
                self.session.commit()
            return model

    def _storage_matches(self, destination: Path, digest: str) -> bool:
        return (
            destination.exists()
            and destination.is_dir()
            and self._content_digest(self._read_files(destination)) == digest
        )

    def get_active(self, pack_id: str) -> AgentPackVersionModel:
        active = self._active(pack_id)
        if active is None:
            raise LookupError("AGENT_PACK_NOT_FOUND")
        return active

    def list_versions(self, pack_id: str) -> list[AgentPackVersionModel]:
        return list(
            self.session.scalars(
                select(AgentPackVersionModel)
                .where(AgentPackVersionModel.pack_id == pack_id)
                .order_by(AgentPackVersionModel.created_at.desc())
            )
        )

    def activate_version(self, version_id: str) -> AgentPackVersionModel:
        model = self.session.get(AgentPackVersionModel, version_id)
        if model is None:
            raise LookupError("AGENT_PACK_VERSION_NOT_FOUND")
        self._activate(model)
        return model

    def preview_base64(self, value: str) -> dict[str, Any]:
        archive_bytes = self._decode_archive(value)
        self.root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".preview-",
            dir=self.root,
        ) as temporary:
            staging = Path(temporary)
            manifest, files = self._validate_and_extract(
                archive_bytes,
                staging,
            )
            active = self._active(str(manifest["id"]))
            old_files = (
                self._read_files(Path(active.storage_uri))
                if active is not None
                else {}
            )
            return {
                "pack_id": manifest["id"],
                "version": manifest["version"],
                "content_digest": self._content_digest(files),
                "added": sorted(set(files) - set(old_files)),
                "removed": sorted(set(old_files) - set(files)),
                "changed": sorted(
                    path
                    for path in set(files).intersection(old_files)
                    if files[path] != old_files[path]
                ),
            }

    def export_base64(
        self,
        pack_id: str,
        selected_paths: list[str] | None = None,
    ) -> str:
        active = self.get_active(pack_id)
        root = Path(active.storage_uri)
        files = self._read_files(root)
        selected = set(selected_paths or files)
        selected.add("agent.yaml")
        if not selected.issubset(files):
            raise AgentPackError("AGENT_PACK_EXPORT_PATH_INVALID")
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for path in sorted(selected):
                archive.writestr(path, files[path])
        return base64.b64encode(buffer.getvalue()).decode("ascii")

    def edit_file(
        self,
        pack_id: str,
        *,
        path: str,
        content: str,
        version: str,
    ) -> AgentPackVersionModel:
        active = self.get_active(pack_id)
        safe_path = PurePosixPath(path.replace("\\", "/"))
        if safe_path.is_absolute() or ".." in safe_path.parts:
            raise AgentPackError("AGENT_PACK_PATH_UNSAFE")
        files = self._read_files(Path(active.storage_uri))
        normalized = safe_path.as_posix()
        if normalized not in files:
            raise AgentPackError("AGENT_PACK_EDIT_PATH_NOT_FOUND")
        files[normalized] = content.encode("utf-8")
        manifest = yaml.safe_load(files["agent.yaml"].decode("utf-8"))
        manifest["version"] = version
        files["agent.yaml"] = yaml.safe_dump(
            manifest,
            allow_unicode=True,
            sort_keys=False,
        ).encode("utf-8")
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            for file_path in sorted(files):
                archive.writestr(file_path, files[file_path])
        return self.import_base64(
            base64.b64encode(buffer.getvalue()).decode("ascii")
        )

    def search(self, pack_id: str, query: str) -> list[dict[str, str]]:
        active = self.get_active(pack_id)
        if self.session.bind is None or self.session.bind.dialect.name != "sqlite":
            return self._fallback_search(active, query)
        self._ensure_fts()
        rows = self.session.execute(
            text(
                """
                SELECT path, snippet(agent_pack_fts, 2, '', '', ' … ', 12)
                FROM agent_pack_fts
                WHERE version_id = :version_id
                  AND agent_pack_fts MATCH :query
                LIMIT 20
                """
            ),
            {"version_id": active.id, "query": query},
        ).all()
        if not rows:
            rows = self.session.execute(
                text(
                    """
                    SELECT path, substr(content, 1, 300)
                    FROM agent_pack_fts
                    WHERE version_id = :version_id
                      AND content LIKE :query
                    LIMIT 20
                    """
                ),
                {
                    "version_id": active.id,
                    "query": f"%{query}%",
                },
            ).all()
        return [{"path": path, "excerpt": excerpt} for path, excerpt in rows]

    def _validate_and_extract(
        self,
        archive_bytes: bytes,
        staging: Path,
    ) -> tuple[dict[str, Any], dict[str, bytes]]:
        try:
            archive = ZipFile(BytesIO(archive_bytes))
        except BadZipFile as error:
            raise AgentPackError("AGENT_PACK_ARCHIVE_INVALID") from error
        with archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise AgentPackError("AGENT_PACK_FILE_LIMIT_EXCEEDED")
            total = sum(info.file_size for info in infos)
            if total > MAX_EXPANDED_BYTES:
                raise AgentPackError("AGENT_PACK_EXPANDED_TOO_LARGE")
            files: dict[str, bytes] = {}
            for info in infos:
                path = PurePosixPath(info.filename.replace("\\", "/"))
                mode = info.external_attr >> 16
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or ":" in path.parts[0]
                    or stat.S_ISLNK(mode)
                ):
                    raise AgentPackError("AGENT_PACK_PATH_UNSAFE")
                if info.is_dir():
                    continue
                if info.compress_size and info.file_size / info.compress_size > 100:
                    raise AgentPackError("AGENT_PACK_COMPRESSION_RATIO_UNSAFE")
                data = archive.read(info)
                relative = path.as_posix()
                files[relative] = data
                target = (staging / relative).resolve()
                if not target.is_relative_to(staging.resolve()):
                    raise AgentPackError("AGENT_PACK_PATH_UNSAFE")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        if "agent.yaml" not in files:
            raise AgentPackError("AGENT_PACK_MANIFEST_MISSING")
        try:
            manifest = yaml.safe_load(files["agent.yaml"].decode("utf-8"))
            schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
            errors = sorted(
                Draft202012Validator(schema).iter_errors(manifest),
                key=lambda item: list(item.path),
            )
        except (UnicodeDecodeError, yaml.YAMLError, json.JSONDecodeError) as error:
            raise AgentPackError("AGENT_PACK_MANIFEST_INVALID") from error
        if errors:
            raise AgentPackError("AGENT_PACK_MANIFEST_INVALID")
        required = {
            str(manifest["entrypoints"]["system"]),
            str(manifest["entrypoints"]["behavior"]),
            str(manifest["capability_config"]),
            *[str(item) for item in manifest.get("memory_paths", [])],
            *[str(item) for item in manifest.get("knowledge_paths", [])],
        }
        if not required.issubset(files):
            raise AgentPackError("AGENT_PACK_REQUIRED_FILE_MISSING")
        for path, data in files.items():
            try:
                if path.endswith((".yaml", ".yml")):
                    yaml.safe_load(data.decode("utf-8"))
                elif path.endswith(".jsonl"):
                    for line in data.decode("utf-8").splitlines():
                        if line.strip():
                            json.loads(line)
                elif path.endswith((".md", ".txt", ".json")):
                    text_value = data.decode("utf-8")
                    if path.endswith(".json"):
                        json.loads(text_value)
            except (UnicodeDecodeError, yaml.YAMLError, json.JSONDecodeError) as error:
                raise AgentPackError("AGENT_PACK_CONTENT_INVALID") from error
        return manifest, files

    @staticmethod
    def _read_files(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
        }

    @staticmethod
    def _decode_archive(value: str) -> bytes:
        try:
            archive_bytes = base64.b64decode(value, validate=True)
        except ValueError as error:
            raise AgentPackError("AGENT_PACK_ARCHIVE_INVALID") from error
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            raise AgentPackError("AGENT_PACK_ARCHIVE_TOO_LARGE")
        return archive_bytes

    @staticmethod
    def _content_digest(files: dict[str, bytes]) -> str:
        digest = hashlib.sha256()
        for path in sorted(files):
            digest.update(path.encode("utf-8"))
            digest.update(b"\0")
            digest.update(files[path])
            digest.update(b"\0")
        return digest.hexdigest()

    def _active(self, pack_id: str) -> AgentPackVersionModel | None:
        return self.session.scalar(
            select(AgentPackVersionModel).where(
                AgentPackVersionModel.pack_id == pack_id,
                AgentPackVersionModel.status == "active",
            )
        )

    def _activate(self, model: AgentPackVersionModel) -> None:
        current = self._active(model.pack_id)
        if current is not None and current.id != model.id:
            current.status = "inactive"
        model.status = "active"
        model.activated_at = utc_now()
        self.session.commit()

    def _ensure_fts(self) -> None:
        self.session.execute(
            text(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS agent_pack_fts
                USING fts5(version_id UNINDEXED, path, content)
                """
            )
        )

    def _index(
        self,
        model: AgentPackVersionModel,
        root: Path,
        files: dict[str, bytes],
    ) -> None:
        if self.session.bind is None or self.session.bind.dialect.name != "sqlite":
            return
        self._ensure_fts()
        self.session.execute(
            text("DELETE FROM agent_pack_fts WHERE version_id = :id"),
            {"id": model.id},
        )
        for path in sorted(files):
            if not path.endswith((".md", ".txt", ".yaml", ".yml", ".jsonl")):
                continue
            content = (root / path).read_text(encoding="utf-8")
            self.session.execute(
                text(
                    """
                    INSERT INTO agent_pack_fts(version_id, path, content)
                    VALUES (:version_id, :path, :content)
                    """
                ),
                {
                    "version_id": model.id,
                    "path": path,
                    "content": content,
                },
            )

    @staticmethod
    def _fallback_search(
        active: AgentPackVersionModel,
        query: str,
    ) -> list[dict[str, str]]:
        root = Path(active.storage_uri)
        matches = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if query.casefold() in content.casefold():
                matches.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "excerpt": content[:300],
                    }
                )
        return matches[:20]


def seed_default_agent_pack(session: Session, root: Path) -> None:
    service = AgentPackService(session, root)
    if service._active("ai-editor") is not None:
        return
    example = PROJECT_ROOT / "agent-packs/examples/ai-editor"
    if not example.exists():
        example = PROJECT_ROOT / "agent-packs/ai-editor"
    if not example.exists():
        return
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for path in sorted(example.rglob("*")):
            if path.is_file():
                archive.writestr(
                    path.relative_to(example).as_posix(),
                    path.read_bytes(),
                )
    service.import_base64(
        base64.b64encode(buffer.getvalue()).decode("ascii"),
        imported_by="system-default",
    )
