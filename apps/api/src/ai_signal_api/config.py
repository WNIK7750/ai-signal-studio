from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_SIGNAL_",
        env_file=".env",
        extra="ignore",
    )

    app_name: str = "AI Signal Studio"
    database_url: str = "sqlite:///data/ai-signal-studio.db"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    timezone: str = "Asia/Shanghai"
    enable_scheduler: bool = True
    disabled_capabilities: list[str] = Field(default_factory=list)
    source_seed_mode: Literal["live", "demo", "none"] = "live"

    # External provider credentials are read only from the process environment
    # or the local, git-ignored .env file.
    llm_provider: Literal["heuristic", "openai_compatible"] = "heuristic"
    llm_api_key: SecretStr | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    llm_max_output_tokens: int = Field(default=1200, ge=128, le=32768)
    model_config_path: Path = Path("config/models.local.json")
    model_secrets_path: Path = Path("config/model-secrets.local.json")

    search_api_key: SecretStr | None = None
    github_token: SecretStr | None = None

    @property
    def llm_configured(self) -> bool:
        return (
            self.llm_provider == "openai_compatible"
            and self.llm_api_key is not None
            and bool(self.llm_api_key.get_secret_value().strip())
            and bool(self.llm_model.strip())
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
