import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

from fakeverse.model import (
    FamilyNameItem,
    FieldSpec,
    FirstNameItem,
    GenerationSettings,
    UniverseFile,
    VocabItem,
    universe_json_schema,
)
from support import FIXTURES, MINIMAL, TEST_WORLD

SCHEMA_FILE = Path(__file__).parents[2] / "schema" / "universe.schema.json"


def test_short_and_long_forms_of_items() -> None:
    assert FirstNameItem.model_validate("Tolman") == FirstNameItem(value="Tolman")
    short = FirstNameItem.model_validate({"en": "Frodo", "fr": "Frodon"})
    assert short.value == {"en": "Frodo", "fr": "Frodon"}
    assert (short.weight, short.gender, short.canon) == (1, None, True)
    long = FirstNameItem.model_validate(
        {"value": "Rosie", "gender": "feminine", "weight": 3, "canon": False}
    )
    assert (long.value, long.gender, long.weight, long.canon) == ("Rosie", "feminine", 3, False)


def test_mapping_with_a_long_form_key_is_a_long_form() -> None:
    with pytest.raises(ValueError, match="value"):
        FirstNameItem.model_validate({"valeu": "Frodo", "gender": "masculine"})


def test_vocab_and_family_items_accept_only_their_keys() -> None:
    assert VocabItem.model_validate({"value": "Old", "weight": 2}).weight == 2
    assert not FamilyNameItem.model_validate({"value": "Took", "canon": False}).canon
    with pytest.raises(ValueError, match="canon"):
        VocabItem.model_validate({"value": "Old", "canon": True})
    with pytest.raises(ValueError, match="gender"):
        FamilyNameItem.model_validate({"value": "Took", "gender": "neutral"})


def test_generation_ratio_steps() -> None:
    assert GenerationSettings().organization_generated_steps == 10
    assert GenerationSettings(organization_generated_ratio=0.15).organization_generated_steps == 3
    assert GenerationSettings(organization_generated_ratio=1).organization_generated_steps == 20


def test_field_spec_bounds() -> None:
    assert FieldSpec.model_validate({"int": "1-5000"}).bounds == (1, 5000)
    assert FieldSpec.model_validate({"vocab": "ship_model"}).bounds is None


def test_universe_defaults() -> None:
    data = yaml.safe_load(MINIMAL.read_text())
    del data["organizations"]
    universe = UniverseFile.model_validate(data)
    assert universe.organizations == []
    assert universe.extensions == {}
    assert universe.generation.organization_generated_ratio == 0.5
    assert universe.place_levels is None


def test_models_are_frozen() -> None:
    universe = UniverseFile.model_validate(yaml.safe_load(MINIMAL.read_text()))
    with pytest.raises(ValueError, match="frozen"):
        universe.format = 2  # type: ignore[misc]


def test_json_schema_is_valid_draft_2020_12() -> None:
    schema = universe_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["title"] == "Fakeverse universe"


def test_committed_schema_is_up_to_date() -> None:
    expected = json.dumps(universe_json_schema(), indent=2, ensure_ascii=False) + "\n"
    assert SCHEMA_FILE.read_text(encoding="utf-8") == expected, (
        "schema/universe.schema.json is out of date: run "
        "`uv run fakeverse schema export > schema/universe.schema.json`"
    )


@pytest.mark.parametrize("path", [TEST_WORLD, MINIMAL], ids=lambda p: p.stem)
def test_json_schema_accepts_valid_files(path: Path) -> None:
    jsonschema.validate(yaml.safe_load(path.read_text()), universe_json_schema())


@pytest.mark.parametrize("name", ["r01-unknown-key", "r02-invalid-id"])
def test_json_schema_rejects_structural_errors(name: str) -> None:
    data: Any = yaml.safe_load((FIXTURES / "invalid" / f"{name}.yaml").read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, universe_json_schema())
