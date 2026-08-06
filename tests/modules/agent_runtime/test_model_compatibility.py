from ai_signal_api.integrations.llm.compatibility import (
    resolve_openai_compatibility,
)
from ai_signal_api.modules.models.service import ResolvedModel


def _model(base_url: str, model_id: str = "model") -> ResolvedModel:
    return ResolvedModel(
        id="model-id",
        name=model_id,
        provider="openai_compatible",
        provider_id="provider-id",
        provider_name="Provider",
        model_id=model_id,
        base_url=base_url,
        api_key="test-only",
        supports_vision=False,
        output_token_limit=None,
        enabled=True,
        is_default=True,
    )


def test_generic_openai_compatible_provider_has_neutral_profile() -> None:
    profile = resolve_openai_compatibility(
        _model("https://api.openai.com/v1", "gpt-compatible")
    )

    assert profile.family == "openai-compatible"
    assert profile.structured_output_method == "function_calling"
    assert profile.extra_body == {}
    assert profile.json_object_retry is True


def test_dashscope_profile_applies_to_provider_not_one_model_name() -> None:
    profile = resolve_openai_compatibility(
        _model(
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "future-model-name",
        )
    )

    assert profile.family == "dashscope-openai-compatible"
    assert profile.json_object_retry is True
    assert profile.extra_body == {"enable_thinking": False}


def test_unknown_openai_compatible_provider_does_not_assume_json_mode() -> None:
    profile = resolve_openai_compatibility(
        _model("https://models.example.com/v1")
    )

    assert profile.family == "openai-compatible"
    assert profile.json_object_retry is False
