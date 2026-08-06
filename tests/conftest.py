import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from ai_signal_api.config import Settings
from ai_signal_api.main import create_app


class FakeModelChat:
    def complete(self, model, message: str, image_urls: list[str]) -> str:
        return f"{model.name}回复：已收到{len(image_urls)}张图片。"


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    del config
    if os.getenv("AI_SIGNAL_RUN_LIVE_MODEL_TESTS") == "1":
        return
    skip_live = pytest.mark.skip(
        reason=(
            "real-model acceptance requires "
            "AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1"
        )
    )
    for item in items:
        if "live_model" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    database_url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    app = create_app(
        settings=Settings(
            _env_file=None,
            database_url=database_url,
            llm_provider="heuristic",
            agent_test_mode=True,
            model_config_path=tmp_path / "models.local.json",
            model_secrets_path=tmp_path / "model-secrets.local.json",
            artifact_root=tmp_path / "artifacts",
            agent_pack_root=tmp_path / "agent-packs",
        ),
        seed_demo_sources=True,
    )
    app.state.model_chat = FakeModelChat()
    with TestClient(app) as test_client:
        yield test_client
