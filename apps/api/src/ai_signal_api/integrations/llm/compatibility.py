from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from ai_signal_api.modules.models.service import ResolvedModel


@dataclass(frozen=True)
class OpenAICompatibilityProfile:
    """Transport-level provider differences, isolated from Agent business logic."""

    family: str = "openai-compatible"
    structured_output_method: str = "function_calling"
    json_object_retry: bool = False
    extra_body: dict[str, object] = field(default_factory=dict)


def resolve_openai_compatibility(
    model: ResolvedModel,
) -> OpenAICompatibilityProfile:
    host = (urlparse(model.base_url).hostname or "").lower()
    if host == "dashscope.aliyuncs.com" or host.endswith(
        ".dashscope.aliyuncs.com"
    ):
        return OpenAICompatibilityProfile(
            family="dashscope-openai-compatible",
            json_object_retry=True,
            extra_body={"enable_thinking": False},
        )
    if host == "api.openai.com" or host.endswith(".openai.com"):
        return OpenAICompatibilityProfile(json_object_retry=True)
    return OpenAICompatibilityProfile()
