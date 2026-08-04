from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import SecretStr

from ai_signal_api.config import Settings


class ProviderConfigurationError(RuntimeError):
    def __init__(self, missing: list[str]) -> None:
        self.code = "LLM_PROVIDER_NOT_CONFIGURED"
        self.missing = tuple(missing)
        super().__init__(
            f"{self.code}: missing {', '.join(self.missing)}"
        )


@dataclass(frozen=True, slots=True)
class LLMRuntimeConfig:
    provider: Literal["openai_compatible"]
    api_key: SecretStr = field(repr=False)
    base_url: str
    model: str
    timeout_seconds: float
    max_output_tokens: int


def resolve_llm_runtime(
    settings: Settings,
) -> LLMRuntimeConfig | None:
    """Resolve provider configuration from the single Settings boundary.

    Provider adapters call this function. They must not call os.getenv(),
    load dotenv files, or keep a second copy of credentials.
    """

    if settings.llm_provider == "heuristic":
        return None

    missing: list[str] = []
    if (
        settings.llm_api_key is None
        or not settings.llm_api_key.get_secret_value().strip()
    ):
        missing.append("AI_SIGNAL_LLM_API_KEY")
    if not settings.llm_model.strip():
        missing.append("AI_SIGNAL_LLM_MODEL")
    if missing:
        raise ProviderConfigurationError(missing)

    return LLMRuntimeConfig(
        provider="openai_compatible",
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url.rstrip("/"),
        model=settings.llm_model.strip(),
        timeout_seconds=settings.llm_timeout_seconds,
        max_output_tokens=settings.llm_max_output_tokens,
    )
