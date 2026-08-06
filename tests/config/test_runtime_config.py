from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.integrations.llm.config import (
    ProviderConfigurationError,
    resolve_llm_runtime,
)
from ai_signal_api.main import create_app


def test_provider_keys_are_loaded_from_environment_and_stay_masked(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AI_SIGNAL_LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("AI_SIGNAL_LLM_API_KEY", "sk-test-secret")
    monkeypatch.setenv("AI_SIGNAL_LLM_MODEL", "configured-model")
    monkeypatch.setenv("AI_SIGNAL_SEARCH_API_KEY", "search-test-secret")
    monkeypatch.setenv("AI_SIGNAL_GITHUB_TOKEN", "github-test-secret")

    settings = Settings(_env_file=None)

    assert settings.llm_configured is True
    assert settings.llm_api_key is not None
    assert settings.llm_api_key.get_secret_value() == "sk-test-secret"
    assert settings.search_api_key is not None
    assert settings.github_token is not None
    serialized = settings.model_dump_json()
    assert "sk-test-secret" not in serialized
    assert "search-test-secret" not in serialized
    assert "github-test-secret" not in serialized


def test_llm_runtime_is_resolved_only_from_settings() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_api_key="sk-test-secret",
        llm_base_url="https://example.test/v1",
        llm_model="configured-model",
    )

    runtime = resolve_llm_runtime(settings)

    assert runtime.provider == "openai_compatible"
    assert runtime.api_key.get_secret_value() == "sk-test-secret"
    assert runtime.base_url == "https://example.test/v1"
    assert runtime.model == "configured-model"


def test_selected_provider_without_required_values_is_locatable() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="openai_compatible",
        llm_api_key=None,
        llm_model="",
    )

    try:
        resolve_llm_runtime(settings)
    except ProviderConfigurationError as error:
        assert error.code == "LLM_PROVIDER_NOT_CONFIGURED"
        assert "AI_SIGNAL_LLM_API_KEY" in error.missing
        assert "AI_SIGNAL_LLM_MODEL" in error.missing
    else:
        raise AssertionError("Expected a provider configuration error")


def test_health_exposes_configuration_state_without_exposing_keys(
    tmp_path,
) -> None:
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'health.db').as_posix()}",
            llm_provider="openai_compatible",
            llm_api_key="sk-test-secret",
            llm_model="configured-model",
            model_config_path=tmp_path / "models.local.json",
            model_secrets_path=tmp_path / "model-secrets.local.json",
        )
    app = create_app(settings=settings, seed_demo_sources=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["providers"]["llm"] == {
        "provider": "openai_compatible",
        "configured": True,
        "model": "configured-model",
    }
    assert body["workflow_version"] == "0.7.0"
    assert "sk-test-secret" not in response.text
