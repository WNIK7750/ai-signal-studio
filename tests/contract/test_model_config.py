import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def test_model_examples_match_the_model_config_contract() -> None:
    contract_dir = ROOT / "contracts" / "05-models"
    schema = json.loads(
        (contract_dir / "model-config.schema.json").read_text(
            encoding="utf-8"
        )
    )
    examples = json.loads(
        (contract_dir / "models.example.json").read_text(encoding="utf-8")
    )

    validator = Draft202012Validator(schema)
    errors = [
        error.message
        for example in examples
        for error in validator.iter_errors(example)
    ]

    assert errors == []
    assert sum(example["is_default"] for example in examples) == 1
