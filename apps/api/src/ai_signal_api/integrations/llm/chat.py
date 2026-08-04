from __future__ import annotations

from typing import Protocol

import httpx

from ai_signal_api.config import Settings
from ai_signal_api.modules.models.service import (
    ModelConfigurationError,
    ResolvedModel,
)


SYSTEM_PROMPT = (
    "你是 AI Signal Studio 的工作区助手。"
    "使用简洁中文直接回答，不虚构未提供的信息。"
)


class ModelChatError(ModelConfigurationError):
    pass


class ModelChat(Protocol):
    def complete(
        self,
        model: ResolvedModel,
        message: str,
        image_urls: list[str],
    ) -> str: ...


class OpenAICompatibleModelChat:
    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings
        self.client = client

    def complete(
        self,
        model: ResolvedModel,
        message: str,
        image_urls: list[str],
    ) -> str:
        if (
            model.provider != "openai_compatible"
            or model.api_key is None
            or not model.api_key.strip()
            or not model.model_id.strip()
            or not model.base_url.strip()
        ):
            raise ModelChatError("MODEL-003")

        user_content: str | list[dict[str, object]]
        if image_urls:
            user_content = [
                {"type": "text", "text": message},
                *[
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    }
                    for image_url in image_urls
                ],
            ]
        else:
            user_content = message

        request_body = {
            "model": model.model_id,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": (
                model.output_token_limit
                or self.settings.llm_max_output_tokens
            ),
        }
        headers = {
            "Authorization": (
                "Bearer "
                f"{model.api_key}"
            ),
            "Content-Type": "application/json",
        }
        endpoint = self._chat_completions_url(model.base_url)

        try:
            if self.client is not None:
                response = self.client.post(
                    endpoint,
                    headers=headers,
                    json=request_body,
                    timeout=self.settings.llm_timeout_seconds,
                )
            else:
                with httpx.Client(
                    timeout=self.settings.llm_timeout_seconds
                ) as client:
                    response = client.post(
                        endpoint,
                        headers=headers,
                        json=request_body,
                    )
            response.raise_for_status()
        except httpx.TimeoutException as error:
            raise ModelChatError("PROVIDER-004") from error
        except httpx.HTTPStatusError as error:
            status_code = error.response.status_code
            if status_code in {401, 403}:
                code = "SECRET-004"
            elif status_code in {400, 404, 405, 422}:
                code = "PROVIDER-003"
            elif status_code in {408, 504}:
                code = "PROVIDER-004"
            elif status_code == 429:
                code = "PROVIDER-005"
            else:
                code = "MODEL-005"
            raise ModelChatError(code) from error
        except httpx.RequestError as error:
            raise ModelChatError("MODEL-005") from error

        try:
            content = response.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ModelChatError("MODEL-006") from error
        if not isinstance(content, str) or not content.strip():
            raise ModelChatError("MODEL-006")
        return content.strip()

    @staticmethod
    def _chat_completions_url(base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"
