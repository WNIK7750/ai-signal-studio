import json
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[2]


def test_all_builtin_themes_match_the_design_token_contract() -> None:
    schema = json.loads(
        (
            ROOT
            / "contracts"
            / "05-design-system"
            / "design-tokens.schema.json"
        ).read_text(encoding="utf-8")
    )
    themes = json.loads(
        (
            ROOT
            / "contracts"
            / "05-design-system"
            / "themes.example.json"
        ).read_text(encoding="utf-8")
    )

    validator = Draft202012Validator(schema)
    errors = [
        error.message
        for theme in themes
        for error in validator.iter_errors(theme)
    ]

    assert errors == []
    assert {theme["id"] for theme in themes} == {
        "signal-light",
        "midnight",
        "paper",
        "forest",
    }
