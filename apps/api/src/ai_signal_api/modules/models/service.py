from __future__ import annotations

import json
import os
import stat
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from ai_signal_api.config import Settings


MODEL_ERROR_MESSAGES = {
    "MODEL-000": "连接成功",
    "MODEL-001": "未找到指定模型",
    "MODEL-002": "当前模型不支持图片",
    "MODEL-003": "模型配置不完整",
    "MODEL-004": "模型名称已存在",
    "MODEL-005": "模型服务调用失败",
    "MODEL-006": "模型返回内容无效",
    "MODEL-007": "内置模型不可修改",
    "MODEL-008": "内置模型无需连接测试",
    "PROVIDER-001": "未找到指定提供商",
    "PROVIDER-002": "提供商配置不完整",
    "PROVIDER-003": "接口地址或模型 ID 不可用",
    "PROVIDER-004": "模型服务请求超时",
    "PROVIDER-005": "模型服务请求受限",
    "SECRET-001": "模型密钥文件无法读取",
    "SECRET-002": "模型密钥文件无法写入",
    "SECRET-003": "请填写 API Key",
    "SECRET-004": "API Key 无效或无权限",
}


class ModelConfigurationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        self.message = MODEL_ERROR_MESSAGES[code]
        super().__init__(f"{code}（{self.message}）")


@dataclass(frozen=True)
class ProviderSummary:
    id: str
    name: str
    base_url: str
    protocol: str
    has_api_key: bool


@dataclass(frozen=True)
class ResolvedModel:
    id: str
    name: str
    provider: str
    provider_id: str
    provider_name: str
    model_id: str
    base_url: str
    api_key: str | None
    supports_vision: bool
    output_token_limit: int | None
    enabled: bool
    is_default: bool
    connection_status: str = "pending"
    connection_checked_at: datetime | None = None
    connection_error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class ModelSelection:
    requested_model_id: str
    effective_model: ResolvedModel

    @property
    def switched(self) -> bool:
        return self.requested_model_id != self.effective_model.id


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return _utc_now()
    return datetime.fromisoformat(value)


def _parse_optional_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class LocalModelConfigStore:
    """File-backed provider/model registry with a separate secret file."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.config_path = settings.model_config_path
        self.secrets_path = settings.model_secrets_path
        self._lock = RLock()

    def ensure_seeded(self) -> None:
        with self._lock:
            if self.config_path.exists():
                return
            now = _utc_now().isoformat()
            providers: list[dict[str, Any]] = []
            secrets: dict[str, str] = {}
            models: list[dict[str, Any]]
            if (
                self.settings.llm_provider == "openai_compatible"
                and self.settings.llm_model.strip()
            ):
                provider_id = "provider_environment"
                providers.append(
                    {
                        "id": provider_id,
                        "name": "环境配置",
                        "protocol": "openai_compatible",
                        "base_url": self.settings.llm_base_url.rstrip("/"),
                        "api_key_ref": provider_id,
                    }
                )
                if self.settings.llm_api_key is not None:
                    key = self.settings.llm_api_key.get_secret_value().strip()
                    if key:
                        secrets[provider_id] = key
                models = [
                    {
                        "id": "model_environment",
                        "name": self.settings.llm_model,
                        "provider_id": provider_id,
                        "model_id": self.settings.llm_model,
                        "supports_vision": False,
                        "output_token_limit": None,
                        "enabled": True,
                        "is_default": True,
                        "connection_status": "pending",
                        "connection_checked_at": None,
                        "connection_error_code": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            else:
                models = [
                    {
                        "id": "model_local",
                        "name": "本地规则模型",
                        "provider_id": "provider_local",
                        "model_id": "local-rules",
                        "supports_vision": False,
                        "output_token_limit": None,
                        "enabled": True,
                        "is_default": True,
                        "connection_status": "not_applicable",
                        "connection_checked_at": None,
                        "connection_error_code": None,
                        "created_at": now,
                        "updated_at": now,
                    }
                ]
            self._write_json(
                self.config_path,
                {"version": 1, "providers": providers, "models": models},
                secret=False,
            )
            if secrets:
                self._write_json(
                    self.secrets_path,
                    {"version": 1, "secrets": secrets},
                    secret=True,
                )

    def read_config(self) -> dict[str, Any]:
        self.ensure_seeded()
        try:
            with self.config_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise ModelConfigurationError("MODEL-003") from error
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("providers"), list)
            or not isinstance(data.get("models"), list)
        ):
            raise ModelConfigurationError("MODEL-003")
        return data

    def read_secrets(self) -> dict[str, str]:
        if not self.secrets_path.exists():
            return {}
        try:
            with self.secrets_path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError, TypeError) as error:
            raise ModelConfigurationError("SECRET-001") from error
        secrets = data.get("secrets") if isinstance(data, dict) else None
        if not isinstance(secrets, dict):
            raise ModelConfigurationError("SECRET-001")
        return {
            str(key): str(value)
            for key, value in secrets.items()
            if isinstance(value, str) and value.strip()
        }

    def write_config(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._write_json(self.config_path, data, secret=False)

    def write_secrets(self, secrets: dict[str, str]) -> None:
        with self._lock:
            self._write_json(
                self.secrets_path,
                {"version": 1, "secrets": secrets},
                secret=True,
            )

    @staticmethod
    def _write_json(
        path: Path,
        data: dict[str, Any],
        *,
        secret: bool,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(
                    data,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                )
                handle.write("\n")
                temporary_path = Path(handle.name)
            os.replace(temporary_path, path)
            if secret:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError as error:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            code = "SECRET-002" if secret else "MODEL-003"
            raise ModelConfigurationError(code) from error


class ModelConfigurationService:
    def __init__(self, store: LocalModelConfigStore) -> None:
        self.store = store

    def list_providers(self) -> list[ProviderSummary]:
        config = self.store.read_config()
        secrets = self.store.read_secrets()
        try:
            return [
                ProviderSummary(
                    id=provider["id"],
                    name=provider["name"],
                    base_url=provider["base_url"],
                    protocol=provider.get(
                        "protocol",
                        "openai_compatible",
                    ),
                    has_api_key=bool(
                        secrets.get(provider["api_key_ref"])
                    ),
                )
                for provider in config["providers"]
            ]
        except (KeyError, TypeError) as error:
            raise ModelConfigurationError("PROVIDER-002") from error

    def list_models(self) -> list[ResolvedModel]:
        config = self.store.read_config()
        secrets = self.store.read_secrets()
        try:
            models = [
                self._resolve_model(model, config["providers"], secrets)
                for model in config["models"]
                if model.get("enabled", True)
            ]
        except (KeyError, TypeError, ValueError) as error:
            raise ModelConfigurationError("MODEL-003") from error
        return sorted(
            models,
            key=lambda model: (
                not model.is_default,
                model.created_at or _utc_now(),
            ),
        )

    def create_model(self, values: dict[str, Any]) -> ResolvedModel:
        config = self.store.read_config()
        secrets = self.store.read_secrets()
        name = str(values["name"]).strip()
        model_id = str(values["model_id"]).strip()
        if not name or not model_id:
            raise ModelConfigurationError("MODEL-003")
        if any(
            model["name"] == name and model.get("enabled", True)
            for model in config["models"]
        ):
            raise ModelConfigurationError("MODEL-004")

        provider_id = values.get("provider_id")
        provider = next(
            (
                item
                for item in config["providers"]
                if item["id"] == provider_id
            ),
            None,
        )
        if provider_id and provider is None:
            raise ModelConfigurationError("PROVIDER-001")
        if provider is None:
            provider_name = str(values.get("provider_name") or "").strip()
            base_url = str(values.get("base_url") or "").strip().rstrip("/")
            if not provider_name or not base_url:
                raise ModelConfigurationError("PROVIDER-002")
            provider_id = f"provider_{uuid4().hex}"
            provider = {
                "id": provider_id,
                "name": provider_name,
                "protocol": "openai_compatible",
                "base_url": base_url,
                "api_key_ref": provider_id,
            }
            config["providers"].append(provider)

        api_key = values.get("api_key")
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        if isinstance(api_key, str) and api_key.strip():
            secrets[provider["api_key_ref"]] = api_key.strip()
        if not secrets.get(provider["api_key_ref"]):
            raise ModelConfigurationError("SECRET-003")

        now = _utc_now()
        is_default = bool(values.get("is_default")) or not any(
            model.get("is_default") for model in config["models"]
        )
        if is_default:
            for model in config["models"]:
                model["is_default"] = False
                model["updated_at"] = now.isoformat()
        model = {
            "id": f"model_{uuid4().hex}",
            "name": name,
            "provider_id": provider["id"],
            "model_id": model_id,
            "supports_vision": bool(values.get("supports_vision")),
            "output_token_limit": values.get("output_token_limit"),
            "enabled": bool(values.get("enabled", True)),
            "is_default": is_default,
            "connection_status": "pending",
            "connection_checked_at": None,
            "connection_error_code": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        config["models"].append(model)
        self.store.write_secrets(secrets)
        self.store.write_config(config)
        return self._resolve_model(model, config["providers"], secrets)

    def update_model(
        self,
        model_id: str,
        values: dict[str, Any],
    ) -> ResolvedModel:
        config = self.store.read_config()
        secrets = self.store.read_secrets()
        model = next(
            (
                item
                for item in config["models"]
                if item["id"] == model_id and item.get("enabled", True)
            ),
            None,
        )
        if model is None:
            raise ModelConfigurationError("MODEL-001")
        if model["provider_id"] == "provider_local":
            raise ModelConfigurationError("MODEL-007")

        name = str(values.get("name", model["name"])).strip()
        runtime_model_id = str(
            values.get("model_id", model["model_id"])
        ).strip()
        if not name or not runtime_model_id:
            raise ModelConfigurationError("MODEL-003")
        if any(
            item["id"] != model_id
            and item["name"] == name
            and item.get("enabled", True)
            for item in config["models"]
        ):
            raise ModelConfigurationError("MODEL-004")

        current_provider = next(
            (
                item
                for item in config["providers"]
                if item["id"] == model["provider_id"]
            ),
            None,
        )
        if current_provider is None:
            raise ModelConfigurationError("PROVIDER-001")

        if "provider_id" in values and values["provider_id"]:
            provider = next(
                (
                    item
                    for item in config["providers"]
                    if item["id"] == values["provider_id"]
                ),
                None,
            )
            if provider is None:
                raise ModelConfigurationError("PROVIDER-001")
            if "provider_name" in values:
                provider_name = str(
                    values.get("provider_name") or ""
                ).strip()
                if not provider_name:
                    raise ModelConfigurationError("PROVIDER-002")
                provider["name"] = provider_name
            if "base_url" in values:
                base_url = str(
                    values.get("base_url") or ""
                ).strip().rstrip("/")
                if not base_url:
                    raise ModelConfigurationError("PROVIDER-002")
                provider["base_url"] = base_url
        elif "provider_id" in values and values["provider_id"] is None:
            provider_name = str(
                values.get("provider_name") or ""
            ).strip()
            base_url = str(values.get("base_url") or "").strip().rstrip("/")
            if not provider_name or not base_url:
                raise ModelConfigurationError("PROVIDER-002")
            provider_id = f"provider_{uuid4().hex}"
            provider = {
                "id": provider_id,
                "name": provider_name,
                "protocol": "openai_compatible",
                "base_url": base_url,
                "api_key_ref": provider_id,
            }
            config["providers"].append(provider)
        else:
            provider = current_provider
            if "provider_name" in values:
                provider_name = str(
                    values.get("provider_name") or ""
                ).strip()
                if not provider_name:
                    raise ModelConfigurationError("PROVIDER-002")
                provider["name"] = provider_name
            if "base_url" in values:
                base_url = str(
                    values.get("base_url") or ""
                ).strip().rstrip("/")
                if not base_url:
                    raise ModelConfigurationError("PROVIDER-002")
                provider["base_url"] = base_url

        api_key = values.get("api_key")
        if hasattr(api_key, "get_secret_value"):
            api_key = api_key.get_secret_value()
        if isinstance(api_key, str) and api_key.strip():
            secrets[provider["api_key_ref"]] = api_key.strip()
        if not secrets.get(provider["api_key_ref"]):
            raise ModelConfigurationError("SECRET-003")

        now = _utc_now().isoformat()
        model.update(
            {
                "name": name,
                "model_id": runtime_model_id,
                "provider_id": provider["id"],
                "updated_at": now,
                "connection_status": "pending",
                "connection_checked_at": None,
                "connection_error_code": None,
            }
        )
        for field in ("supports_vision", "output_token_limit"):
            if field in values:
                model[field] = values[field]
        if values.get("is_default"):
            for item in config["models"]:
                item["is_default"] = item["id"] == model_id
                item["updated_at"] = now

        self.store.write_secrets(secrets)
        self.store.write_config(config)
        return self._resolve_model(model, config["providers"], secrets)

    def delete_model(self, model_id: str) -> None:
        config = self.store.read_config()
        model = next(
            (
                item
                for item in config["models"]
                if item["id"] == model_id and item.get("enabled", True)
            ),
            None,
        )
        if model is None:
            raise ModelConfigurationError("MODEL-001")
        if model["provider_id"] == "provider_local":
            raise ModelConfigurationError("MODEL-007")

        was_default = bool(model.get("is_default"))
        now = _utc_now().isoformat()
        model["enabled"] = False
        model["is_default"] = False
        model["updated_at"] = now
        if was_default:
            fallback = next(
                (
                    item
                    for item in config["models"]
                    if item.get("enabled", True)
                ),
                None,
            )
            if fallback is None:
                raise ModelConfigurationError("MODEL-003")
            fallback["is_default"] = True
            fallback["updated_at"] = now
        self.store.write_config(config)

    def activate_model(self, model_id: str) -> ResolvedModel:
        config = self.store.read_config()
        secrets = self.store.read_secrets()
        target = next(
            (
                model
                for model in config["models"]
                if model["id"] == model_id and model.get("enabled", True)
            ),
            None,
        )
        if target is None:
            raise ModelConfigurationError("MODEL-001")
        resolved_target = self._resolve_model(
            target,
            config["providers"],
            secrets,
        )
        if (
            resolved_target.provider == "openai_compatible"
            and not resolved_target.has_api_key
        ):
            raise ModelConfigurationError("SECRET-003")
        now = _utc_now().isoformat()
        for model in config["models"]:
            model["is_default"] = model["id"] == model_id
            model["updated_at"] = now
        self.store.write_config(config)
        return self._resolve_model(
            target,
            config["providers"],
            secrets,
        )

    def test_model_connection(self, model_id: str, model_chat: Any) -> None:
        selection = self.select_for_request(model_id)
        model = selection.effective_model
        if model.provider == "heuristic":
            raise ModelConfigurationError("MODEL-008")
        if not model.has_api_key:
            raise ModelConfigurationError("SECRET-003")
        try:
            model_chat.complete(model, "请只回复 OK", [])
        except ModelConfigurationError as error:
            self._set_connection_state(
                model_id,
                status="error",
                error_code=error.code,
                checked=True,
            )
            raise
        except Exception as error:
            self._set_connection_state(
                model_id,
                status="error",
                error_code="MODEL-005",
                checked=True,
            )
            raise ModelConfigurationError("MODEL-005") from error
        self._set_connection_state(
            model_id,
            status="healthy",
            error_code=None,
            checked=True,
        )

    def mark_needs_retest(
        self,
        model_id: str,
        error_code: str,
    ) -> None:
        """Flag a likely provider-side failure without making another call."""

        self._set_connection_state(
            model_id,
            status="needs_retest",
            error_code=error_code,
            checked=False,
        )

    def _set_connection_state(
        self,
        model_id: str,
        *,
        status: str,
        error_code: str | None,
        checked: bool,
    ) -> None:
        config = self.store.read_config()
        target = next(
            (
                item
                for item in config["models"]
                if item["id"] == model_id and item.get("enabled", True)
            ),
            None,
        )
        if target is None:
            raise ModelConfigurationError("MODEL-001")
        if target["provider_id"] == "provider_local":
            return
        target["connection_status"] = status
        target["connection_error_code"] = error_code
        target["connection_checked_at"] = (
            _utc_now().isoformat() if checked else None
        )
        self.store.write_config(config)

    def select_for_request(
        self,
        requested_model_id: str | None,
    ) -> ModelSelection:
        models = self.list_models()
        selected = next(
            (
                model
                for model in models
                if (
                    model.id == requested_model_id
                    if requested_model_id
                    else model.is_default
                )
                and model.enabled
            ),
            None,
        )
        if selected is None and not requested_model_id:
            selected = next((model for model in models if model.enabled), None)
        if selected is None:
            raise ModelConfigurationError("MODEL-001")
        return ModelSelection(selected.id, selected)

    @staticmethod
    def _resolve_model(
        model: dict[str, Any],
        providers: list[dict[str, Any]],
        secrets: dict[str, str],
    ) -> ResolvedModel:
        if model["provider_id"] == "provider_local":
            return ResolvedModel(
                id=model["id"],
                name=model["name"],
                provider="heuristic",
                provider_id="provider_local",
                provider_name="内置",
                model_id=model["model_id"],
                base_url="local://heuristic",
                api_key=None,
                supports_vision=bool(model.get("supports_vision")),
                output_token_limit=model.get("output_token_limit"),
                enabled=bool(model.get("enabled", True)),
                is_default=bool(model.get("is_default")),
                connection_status="not_applicable",
                connection_checked_at=None,
                connection_error_code=None,
                created_at=_parse_datetime(model.get("created_at")),
                updated_at=_parse_datetime(model.get("updated_at")),
            )
        provider = next(
            (
                item
                for item in providers
                if item["id"] == model["provider_id"]
            ),
            None,
        )
        if provider is None:
            raise ModelConfigurationError("PROVIDER-001")
        return ResolvedModel(
            id=model["id"],
            name=model["name"],
            provider=provider.get("protocol", "openai_compatible"),
            provider_id=provider["id"],
            provider_name=provider["name"],
            model_id=model["model_id"],
            base_url=provider["base_url"],
            api_key=secrets.get(provider["api_key_ref"]),
            supports_vision=bool(model.get("supports_vision")),
            output_token_limit=model.get("output_token_limit"),
            enabled=bool(model.get("enabled", True)),
            is_default=bool(model.get("is_default")),
            connection_status=str(
                model.get("connection_status", "pending")
            ),
            connection_checked_at=_parse_optional_datetime(
                model.get("connection_checked_at")
            ),
            connection_error_code=model.get("connection_error_code"),
            created_at=_parse_datetime(model.get("created_at")),
            updated_at=_parse_datetime(model.get("updated_at")),
        )


def build_model_configuration_service(
    settings: Settings,
) -> ModelConfigurationService:
    store = LocalModelConfigStore(settings)
    store.ensure_seeded()
    return ModelConfigurationService(store)
