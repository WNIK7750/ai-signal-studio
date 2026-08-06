from pathlib import Path

import yaml

from ai_signal_api.agent_runtime.tools import TOOL_SCHEMAS


ROOT = Path(__file__).resolve().parents[2]


def test_intelligence_domain_tools_are_declared_and_schema_backed() -> None:
    domain = yaml.safe_load(
        (
            ROOT
            / "apps/api/src/ai_signal_api/modules/intelligence/agent/domain.yaml"
        ).read_text(encoding="utf-8")
    )
    catalog = yaml.safe_load(
        (
            ROOT / "contracts/01-capabilities/capability-catalog.yaml"
        ).read_text(encoding="utf-8")
    )
    catalog_ids = {item["id"] for item in catalog["capabilities"]}

    for capability_id in domain["capabilities"]:
        if capability_id.startswith("research."):
            assert capability_id in catalog_ids
            assert capability_id in TOOL_SCHEMAS
            assert TOOL_SCHEMAS[capability_id].model_json_schema()["type"] == (
                "object"
            )
