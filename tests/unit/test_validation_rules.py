"""One test per validation rule of the universe guide, with a minimal invalid file per rule."""

import copy
from pathlib import Path
from typing import Any

import pytest

from fakeverse.loader import MAX_FILE_SIZE, load_file
from fakeverse.validation import Issue, format_path, validate_data
from support import INVALID, MINIMAL, TEST_WORLD

# file name -> (rule, expected error codes and paths)
INVALID_FILES: dict[str, set[tuple[str, str]]] = {
    "r01-unknown-key": {("schema", "places[2].color")},
    "r01-duplicate-key": {("duplicate-key", "places[2].level")},
    "r01-yaml-syntax": {("yaml-syntax", "<root>")},
    "r01-yaml-alias": {("yaml-alias", "<root>")},
    "r02-id-mismatch": {("id-mismatch", "universe.id")},
    "r02-invalid-id": {("schema", "places[2].id")},
    "r03-duplicate-id": {("duplicate-id", "organizations[1].id")},
    "r04-unknown-parent": {("unknown-reference", "places[2].parent")},
    "r04-unknown-homeland": {("unknown-reference", "peoples[0].homelands[0]")},
    "r04-unknown-vocab": {("unknown-reference", "patterns.street_address.en")},
    "r05-area-with-parent": {("place-hierarchy", "places[0].parent")},
    "r05-locality-under-locality": {("place-hierarchy", "places[3].parent")},
    "r06-homeland-without-locality": {("no-locality", "peoples[0].homelands[1]")},
    "r07-undeclared-locale": {("locale-not-declared", "places[2].name.de")},
    "r07-missing-default-locale": {("missing-default-locale", "places[2].name")},
    "r08-invalid-locale": {("invalid-locale", "universe.locales[2]")},
    "r09-pattern-syntax": {("invalid-pattern", "patterns.postal_code")},
    "r09-field-not-allowed": {("pattern-field-not-allowed", "patterns.phone")},
    "r10-no-locality": {
        ("minimum-data", "places"),
        ("no-locality", "peoples[0].homelands[0]"),
    },
    "r10-no-people": {("minimum-data", "peoples")},
    "r11-string-too-long": {("string-too-long", "organizations[0].name.fr")},
    "r13-reserved-extension-id": {("reserved-extension-id", "extensions.person")},
}


def errors_of(issues: list[Issue]) -> set[tuple[str, str]]:
    return {(i.code, format_path(i.path)) for i in issues if i.severity == "error"}


def warnings_of(issues: list[Issue]) -> set[tuple[str, str]]:
    return {(i.code, format_path(i.path)) for i in issues if i.severity == "warning"}


def test_every_invalid_fixture_is_listed() -> None:
    assert {path.stem for path in INVALID.glob("*.yaml")} == set(INVALID_FILES)


@pytest.mark.parametrize("name", sorted(INVALID_FILES))
def test_invalid_file_breaks_exactly_its_rule(name: str) -> None:
    result = load_file(INVALID / f"{name}.yaml")
    assert result.universe is None
    assert errors_of(result.issues) == INVALID_FILES[name]
    assert all(issue.line is not None for issue in result.errors)
    assert all(issue.file == str(INVALID / f"{name}.yaml") for issue in result.issues)


def test_minimal_file_is_valid_without_warning() -> None:
    result = load_file(MINIMAL)
    assert result.universe is not None
    assert result.issues == []


def test_test_world_is_valid_with_expected_warnings() -> None:
    result = load_file(TEST_WORLD)
    assert result.universe is not None
    assert not result.errors
    assert warnings_of(result.issues) == {
        ("translation-coverage", "universe.locales[1]"),
        ("small-name-pool", "peoples[1].first_names"),
        ("small-name-pool", "peoples[2].first_names"),
    }
    assert not result.is_valid(strict=True)


def test_rule_12_file_too_large(tmp_path: Path) -> None:
    path = tmp_path / "huge.yaml"
    path.write_bytes(b"#" * MAX_FILE_SIZE)
    result = load_file(path)
    assert errors_of(result.issues) == {("file-too-large", "<root>")}


def test_error_lines_point_to_the_value() -> None:
    result = load_file(INVALID / "r04-unknown-parent.yaml")
    lines = (INVALID / "r04-unknown-parent.yaml").read_text().splitlines()
    (issue,) = result.errors
    assert issue.line is not None
    assert lines[issue.line - 1].strip() == "parent: nowhere"


# Inline variants of the minimal universe, for the finer points of each rule.


def check(data: dict[str, Any], expected_id: str | None = "minimal") -> list[Issue]:
    _universe, issues = validate_data(data, expected_id=expected_id)
    return issues


def test_rule_1_missing_key_and_format_version(minimal_data: dict[str, Any]) -> None:
    del minimal_data["places"][0]["name"]
    minimal_data["format"] = 2
    assert errors_of(check(minimal_data)) == {
        ("schema", "format"),
        ("schema", "places[0].name"),
    }
    messages = {i.message for i in check(minimal_data)}
    assert "Missing required key 'name'" in messages
    assert "Unsupported format version; expected 1" in messages


def test_rule_1_root_must_be_a_mapping() -> None:
    assert errors_of(check([1, 2])) == {("schema", "<root>")}  # type: ignore[arg-type]


def test_rule_1_gender_only_in_first_names(minimal_data: dict[str, Any]) -> None:
    minimal_data["peoples"][0]["family_names"] = [{"value": "Smith", "gender": "feminine"}]
    minimal_data["vocab"]["street"] = [{"value": "Street", "canon": False}]
    assert errors_of(check(minimal_data)) == {
        ("schema", "peoples[0].family_names[0].gender"),
        ("schema", "vocab.street[0].canon"),
    }


def test_rule_1_weight_bounds(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][0]["weight"] = 0
    minimal_data["places"][1]["weight"] = 1001
    minimal_data["places"][2]["weight"] = True
    assert errors_of(check(minimal_data)) == {
        ("schema", "places[0].weight"),
        ("schema", "places[1].weight"),
        ("schema", "places[2].weight"),
    }


def test_rule_1_organization_ratio_steps(minimal_data: dict[str, Any]) -> None:
    for ok in (0, 0.15, 0.35, 1):
        minimal_data["generation"] = {"organization_generated_ratio": ok}
        assert not errors_of(check(minimal_data)), ok
    for bad in (0.12, 1.05, -0.05):
        minimal_data["generation"] = {"organization_generated_ratio": bad}
        assert errors_of(check(minimal_data)) == {
            ("schema", "generation.organization_generated_ratio")
        }


def test_rule_1_extension_forms(minimal_data: dict[str, Any]) -> None:
    minimal_data["extensions"] = {
        "both": {
            "label": "Both",
            "items": [{"id": "a", "name": "A"}],
            "fields": {"x": {"int": "1-2"}},
        },
        "neither": {"label": "Neither"},
        "multi": {"label": "Multi", "fields": {"x": {"vocab": "street", "int": "1-2"}}},
        "range": {"label": "Range", "fields": {"x": {"int": "9-1"}}},
        "bad-field-name": {"label": "Bad", "fields": {"Bad-Name": {"int": "1-2"}}},
    }
    assert errors_of(check(minimal_data)) == {
        ("schema", "extensions.both"),
        ("schema", "extensions.neither"),
        ("schema", "extensions.multi.fields.x"),
        ("schema", "extensions.range.fields.x"),
        ("schema", "extensions.bad-field-name.fields.Bad-Name"),
    }


def test_rule_1_localized_shapes(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][0]["name"] = ""
    minimal_data["places"][1]["name"] = {}
    minimal_data["places"][2]["name"] = {"en": 3}
    minimal_data["universe"]["name"] = 42
    assert errors_of(check(minimal_data)) == {
        ("schema", "places[0].name"),
        ("schema", "places[1].name"),
        ("schema", "places[2].name"),
        ("schema", "universe.name"),
    }


def test_rule_2_id_checked_only_against_given_name(minimal_data: dict[str, Any]) -> None:
    assert not errors_of(check(minimal_data, expected_id=None))
    assert errors_of(check(minimal_data, expected_id="other")) == {("id-mismatch", "universe.id")}


def test_rule_3_duplicate_ids_in_every_collection(minimal_data: dict[str, Any]) -> None:
    minimal_data["peoples"].append(copy.deepcopy(minimal_data["peoples"][0]))
    minimal_data["places"].append(copy.deepcopy(minimal_data["places"][2]))
    minimal_data["extensions"] = {
        "relic": {"label": "Relic", "items": [{"id": "a", "name": "A"}, {"id": "a", "name": "B"}]}
    }
    assert errors_of(check(minimal_data)) == {
        ("duplicate-id", "peoples[1].id"),
        ("duplicate-id", "places[3].id"),
        ("duplicate-id", "extensions.relic.items[1].id"),
    }


def test_rule_4_other_references(minimal_data: dict[str, Any]) -> None:
    minimal_data["organizations"][0]["places"] = ["atlantis"]
    minimal_data["extensions"] = {
        "ship": {
            "label": "Ship",
            "fields": {"cargo": {"vocab": "cargo"}, "home": {"place": "locality"}},
        },
        "tower": {"label": "Tower", "fields": {"spot": {"place": "area"}}},
    }
    minimal_data["places"][0]["patterns"] = {"street_address": "{vocab.road}"}
    assert errors_of(check(minimal_data)) == {
        ("unknown-reference", "organizations[0].places[0]"),
        ("unknown-reference", "extensions.ship.fields.cargo.vocab"),
        ("unknown-reference", "places[0].patterns.street_address"),
    }


def test_rule_4_extension_place_level_must_exist(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"] = [minimal_data["places"][0], minimal_data["places"][2]]
    minimal_data["places"][1]["parent"] = "land"
    minimal_data["peoples"][0]["homelands"] = ["land"]
    minimal_data["extensions"] = {
        "ship": {"label": "Ship", "fields": {"x": {"place": "subdivision"}}}
    }
    assert errors_of(check(minimal_data)) == {
        ("unknown-reference", "extensions.ship.fields.x.place")
    }


def test_rule_5_required_parents(minimal_data: dict[str, Any]) -> None:
    del minimal_data["places"][1]["parent"]
    minimal_data["places"].append({"id": "orphan", "level": "locality", "name": "Orphan"})
    minimal_data["places"].append(
        {"id": "nested", "level": "subdivision", "parent": "county", "name": "Nested"}
    )
    assert errors_of(check(minimal_data)) == {
        ("place-hierarchy", "places[1].parent"),
        ("place-hierarchy", "places[3].parent"),
        ("place-hierarchy", "places[4].parent"),
    }


def test_rule_5_locality_directly_under_area_is_valid(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][2]["parent"] = "land"
    minimal_data["peoples"][0]["homelands"] = ["land"]
    assert not errors_of(check(minimal_data))


def test_rule_6_organization_places_need_a_locality(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"].append({"id": "wild", "level": "area", "name": "Wild"})
    minimal_data["organizations"][0]["places"] = ["wild"]
    assert errors_of(check(minimal_data)) == {("no-locality", "organizations[0].places[0]")}


def test_rule_7_every_kind_of_mapping(minimal_data: dict[str, Any]) -> None:
    minimal_data["universe"]["sources"]["translations"] = {"fr": "Someone", "de": "Jemand"}
    minimal_data["universe"]["default_locale"] = "es"
    minimal_data["universe"]["locales"] = ["en", "fr", "fr"]
    issues = errors_of(check(minimal_data))
    assert ("locale-not-declared", "universe.sources.translations.de") in issues
    assert ("locale-not-declared", "universe.default_locale") in issues
    assert ("duplicate-locale", "universe.locales[2]") in issues
    assert ("missing-default-locale", "universe.name") in issues


def test_rule_7_translations_do_not_need_the_default(minimal_data: dict[str, Any]) -> None:
    minimal_data["universe"]["sources"]["translations"] = {"fr": "Someone"}
    assert not errors_of(check(minimal_data))


def test_rule_8_invalid_locale_keys(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][0]["name"] = {"en": "Land", "fr_FR": "Terre", "xx-yyyyy": "?"}
    minimal_data["universe"]["default_locale"] = "EN"
    assert errors_of(check(minimal_data)) == {
        ("invalid-locale", "places[0].name.fr_FR"),
        ("invalid-locale", "places[0].name.xx-yyyyy"),
        ("invalid-locale", "universe.default_locale"),
    }


def test_rule_9_pattern_contexts(minimal_data: dict[str, Any]) -> None:
    minimal_data["patterns"]["street_address"] = "{int:1-9} {first_name}"
    minimal_data["patterns"]["address_format"] = "{street_address} {postal_code} {people}"
    minimal_data["patterns"]["organization_name"] = "{area} {family_name}"
    minimal_data["peoples"][0]["name_format"] = "{first_name} of {locality} {street_address}"
    minimal_data["extensions"] = {
        "ship": {
            "label": "Ship",
            "fields": {
                "code": {"pattern": "{name}-{digits:2}"},
                "name": {"pattern": "{vocab.street}"},
                "plate": {"pattern": "{name}-{code}"},
            },
        }
    }
    assert errors_of(check(minimal_data)) == {
        ("pattern-field-not-allowed", "patterns.street_address"),
        ("pattern-field-not-allowed", "patterns.address_format"),
        ("pattern-field-not-allowed", "patterns.organization_name"),
        ("pattern-field-not-allowed", "peoples[0].name_format"),
        ("pattern-field-not-allowed", "extensions.ship.fields.code.pattern"),
    }


def test_rule_9_pattern_overrides_and_localized_variants(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][1]["patterns"] = {"phone": {"en": "{digits:3}", "fr": "{digits:3"}}
    assert errors_of(check(minimal_data)) == {("invalid-pattern", "places[1].patterns.phone.fr")}


def test_rule_9_unknown_pattern_names(minimal_data: dict[str, Any]) -> None:
    minimal_data["patterns"]["nickname"] = "{first_name}"
    minimal_data["places"][0]["patterns"] = {"email": "{first_name}@x.org"}
    assert errors_of(check(minimal_data)) == {
        ("schema", "patterns.nickname"),
        ("schema", "places[0].patterns.email"),
    }


def test_rule_11_sources_have_a_larger_limit(minimal_data: dict[str, Any]) -> None:
    minimal_data["universe"]["sources"]["scope"] = "S" * 200
    assert not errors_of(check(minimal_data))
    minimal_data["universe"]["sources"]["scope"] = "S" * 201
    assert errors_of(check(minimal_data)) == {("string-too-long", "universe.sources.scope")}


def test_rule_11_applies_to_keys_and_lists(minimal_data: dict[str, Any]) -> None:
    minimal_data["peoples"][0]["first_names"].append("N" * 81)
    assert errors_of(check(minimal_data)) == {("string-too-long", "peoples[0].first_names[10]")}


def test_extension_items_fields(minimal_data: dict[str, Any]) -> None:
    minimal_data["extensions"] = {
        "relic": {
            "label": "Relic",
            "items": [
                {"id": "a", "name": "A", "fields": {"kind": "Stone", "age": 3}},
                {"id": "b", "name": "B", "fields": {"age": 4, "kind": "Glass"}},
                {"id": "c", "name": "C", "fields": {"kind": "Wood"}},
                {"id": "d", "name": "D", "fields": {"kind": "Iron", "age": 1, "name": "X"}},
            ],
        }
    }
    assert errors_of(check(minimal_data)) == {
        ("inconsistent-fields", "extensions.relic.items[2].fields"),
        ("inconsistent-fields", "extensions.relic.items[3].fields"),
        ("reserved-field", "extensions.relic.items[3].fields.name"),
    }


def test_reserved_template_extension_id(minimal_data: dict[str, Any]) -> None:
    minimal_data["extensions"] = {"template": {"label": "T", "fields": {"x": {"int": "1-2"}}}}
    assert errors_of(check(minimal_data)) == {("reserved-extension-id", "extensions.template")}


def test_warning_translation_coverage(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"][0]["name"] = {"en": "Land"}
    issues = check(minimal_data)
    assert warnings_of(issues) == {("translation-coverage", "universe.locales[1]")}
    (warning,) = issues
    assert "places[0].name" in warning.message


def test_warning_small_name_pool(minimal_data: dict[str, Any]) -> None:
    minimal_data["peoples"][0]["first_names"] = minimal_data["peoples"][0]["first_names"][:9]
    assert warnings_of(check(minimal_data)) == {("small-name-pool", "peoples[0].first_names")}


def test_warning_type_not_supported(minimal_data: dict[str, Any]) -> None:
    del minimal_data["patterns"]["email"]
    del minimal_data["patterns"]["postal_code"]
    issues = check(minimal_data)
    assert warnings_of(issues) == {("type-not-supported", "<root>")}
    assert sorted(i.message.split("'")[1] for i in issues) == ["email", "postal_code"]


def test_rule_9_patterns_of_required_values_cannot_be_empty(minimal_data: dict[str, Any]) -> None:
    minimal_data["patterns"]["street_address"] = "{subdivision}"
    minimal_data["patterns"]["address_format"] = "{postal_code}, {subdivision}"
    minimal_data["patterns"]["organization_name"] = "{subdivision}."
    minimal_data["peoples"][0]["name_format"] = "{family_name}"  # valid: folk has family names
    minimal_data["extensions"] = {
        "ship": {"label": "Ship", "fields": {"a": {"int": "1-2"}, "b": {"pattern": " - "}}}
    }
    assert errors_of(check(minimal_data)) == {
        ("pattern-may-be-empty", "patterns.street_address"),
        ("pattern-may-be-empty", "patterns.address_format"),
        ("pattern-may-be-empty", "patterns.organization_name"),
        ("pattern-may-be-empty", "extensions.ship.fields.b.pattern"),
    }
    del minimal_data["peoples"][0]["family_names"]
    assert ("pattern-may-be-empty", "peoples[0].name_format") in errors_of(check(minimal_data))


def test_rule_9_optional_values_may_be_empty(minimal_data: dict[str, Any]) -> None:
    minimal_data["patterns"]["postal_code"] = "{subdivision}"
    minimal_data["patterns"]["email"] = "{family_name}"
    minimal_data["places"][1]["patterns"] = {"street_address": "{locality}"}
    assert not errors_of(check(minimal_data))
