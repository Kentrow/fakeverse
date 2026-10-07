from typing import Any

from fakeverse.capabilities import compute_capabilities
from fakeverse.loader import load_file
from fakeverse.model import UniverseFile
from fakeverse.types import CORE_TYPES
from support import TEST_WORLD


def universe_of(data: dict[str, Any]) -> UniverseFile:
    return UniverseFile.model_validate(data)


def test_minimal_supports_every_core_type(minimal_data: dict[str, Any]) -> None:
    capabilities = compute_capabilities(universe_of(minimal_data))
    assert capabilities.core == CORE_TYPES
    assert capabilities.unsupported == {}
    assert capabilities.extensions == ()


def test_test_world_capabilities() -> None:
    universe = load_file(TEST_WORLD).universe
    assert universe is not None
    capabilities = compute_capabilities(universe)
    assert capabilities.core == CORE_TYPES
    assert [(ext.id, ext.fields) for ext in capabilities.extensions] == [
        ("relic", ("name", "kind", "age")),
        ("barge", ("name", "registry", "cargo", "home_port", "region", "crew", "owner", "plate")),
    ]
    assert capabilities.supports("barge")
    assert capabilities.supports("person")
    assert not capabilities.supports("starship")


def test_address_needs_street_address_for_every_locality(minimal_data: dict[str, Any]) -> None:
    del minimal_data["patterns"]["street_address"]
    minimal_data["places"][1]["patterns"] = {"street_address": "{int:1-9} Road"}
    assert "address" in compute_capabilities(universe_of(minimal_data)).core
    minimal_data["places"].append(
        {"id": "far", "level": "locality", "parent": "land", "name": "Far"}
    )
    capabilities = compute_capabilities(universe_of(minimal_data))
    assert capabilities.unsupported["address"].startswith("some localities")
    assert capabilities.unsupported["person"] == capabilities.unsupported["address"]
    assert capabilities.unsupported["organization_name"] == capabilities.unsupported["address"]


def test_optional_patterns(minimal_data: dict[str, Any]) -> None:
    for name in ("email", "username", "phone", "postal_code"):
        del minimal_data["patterns"][name]
    unsupported = compute_capabilities(universe_of(minimal_data)).unsupported
    assert set(unsupported) == {"email", "username", "phone", "postal_code"}


def test_phone_override_must_reach_a_homeland(minimal_data: dict[str, Any]) -> None:
    del minimal_data["patterns"]["phone"]
    minimal_data["places"].append({"id": "isle", "level": "area", "name": "Isle"})
    minimal_data["places"].append(
        {
            "id": "port",
            "level": "locality",
            "parent": "isle",
            "name": "Port",
            "patterns": {"phone": "{digits:5}"},
        }
    )
    assert "phone" in compute_capabilities(universe_of(minimal_data)).unsupported
    minimal_data["peoples"][0]["homelands"].append("isle")
    assert "phone" in compute_capabilities(universe_of(minimal_data)).core


def test_last_name_subdivision_and_organization(minimal_data: dict[str, Any]) -> None:
    del minimal_data["peoples"][0]["family_names"]
    minimal_data["places"][2]["parent"] = "land"
    minimal_data["peoples"][0]["homelands"] = ["land"]
    del minimal_data["organizations"]
    unsupported = compute_capabilities(universe_of(minimal_data)).unsupported
    assert set(unsupported) == {"last_name", "subdivision", "organization", "organization_name"}
    minimal_data["patterns"]["organization_name"] = "The {vocab.street}"
    assert "organization" in compute_capabilities(universe_of(minimal_data)).core


def test_no_locality_and_no_people(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"] = minimal_data["places"][:2]
    minimal_data["peoples"] = []
    unsupported = compute_capabilities(universe_of(minimal_data)).unsupported
    assert unsupported["address"] == "no locality"
    assert set(unsupported) == set(CORE_TYPES)


def test_people_without_reachable_locality(minimal_data: dict[str, Any]) -> None:
    minimal_data["places"].append({"id": "wild", "level": "area", "name": "Wild"})
    minimal_data["peoples"][0]["homelands"] = ["wild"]
    unsupported = compute_capabilities(universe_of(minimal_data)).unsupported
    assert unsupported["person"] == "no locality in the homelands of the peoples"
    assert "address" not in unsupported
