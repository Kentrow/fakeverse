"""The coherence checker accepts generated data and catches every kind of broken invariant."""

import copy
from typing import Any

import pytest

from fakeverse import Fakeverse, UniverseGenerator
from fakeverse.coherence import Violation, check_items, check_universe


def test_fixture_is_coherent(fv: Fakeverse) -> None:
    assert check_universe(fv, "test-world", count=60, seed=3) == []


def first(world: UniverseGenerator, type_id: str, predicate: Any = None) -> dict[str, Any]:
    for item in world.generate(type_id, 200, seed=1).items:
        if predicate is None or predicate(item):
            return copy.deepcopy(item)
    raise AssertionError("no matching item")


def broken(world: UniverseGenerator, type_id: str, item: Any) -> list[str]:
    return check_items(world, type_id, [item])


def test_address_invariants(world: UniverseGenerator) -> None:
    address = first(world, "address", lambda a: a["locality"] == "Millbrook")
    assert broken(world, "address", address) == []
    address["area"] = "South March"
    assert "invariant 1" in broken(world, "address", address)[0]
    address["street_address"] = ""
    assert "invariant 7: 'street_address' is empty" in broken(world, "address", address)[0]


def test_person_invariants(world: UniverseGenerator) -> None:
    person = first(world, "person", lambda p: p["people"] == "Valefolk")
    assert broken(world, "person", person) == []

    moved = copy.deepcopy(person)
    moved["address"] = first(world, "address", lambda a: a["locality"] == "Dunmere")
    assert any("invariant 2" in m for m in broken(world, "person", moved))

    renamed = copy.deepcopy(person)
    renamed["first_name"] = "Reed"
    assert any("invariant 3" in m for m in broken(world, "person", renamed))

    regendered = copy.deepcopy(person)
    regendered["gender"] = "neutral" if person["first_name"] in {"Aldo", "Elna"} else "x"
    if person["first_name"] not in {"Ivo", "Jory"}:
        assert any("invariant 3" in m for m in broken(world, "person", regendered))

    no_family = copy.deepcopy(person)
    no_family["last_name"] = None
    assert any("invariant 4" in m for m in broken(world, "person", no_family))

    email = copy.deepcopy(person)
    email["email"] = "someone@post.example"
    assert any("invariant 5" in m for m in broken(world, "person", email))

    unknown = copy.deepcopy(person)
    unknown["people"] = "Dwarf"
    assert broken(world, "person", unknown) == ["#0: unknown people 'Dwarf'"]


def test_organization_invariants(world: UniverseGenerator) -> None:
    guild = first(world, "organization", lambda o: o["name"] == "Copper Guild")
    assert broken(world, "organization", guild) == []
    guild["address"] = first(world, "address", lambda a: a["locality"] == "Millbrook")
    assert any("invariant 6" in m for m in broken(world, "organization", guild))


def test_atomic_and_extension_invariants(world: UniverseGenerator) -> None:
    assert broken(world, "last_name", None) == ["#0: invariant 7: 'last_name' is null"]
    assert broken(world, "postal_code", None) == []
    assert broken(world, "first_name", "") == ["#0: invariant 7: 'first_name' is empty"]
    assert broken(world, "barge", {"name": "X", "crew": None}) == [
        "#0: invariant 7: 'crew' is null"
    ]


def test_violation_format() -> None:
    violation = Violation("lotr", "fr", "person", 3, "invariant 2: oops")
    assert violation.format() == "lotr [fr] person #3: invariant 2: oops"


@pytest.mark.parametrize("locale", ["en", "fr"])
def test_check_items_on_generated_data(fv: Fakeverse, locale: str) -> None:
    generator = fv.universe("test-world", locale)
    for type_id in generator.capabilities().core:
        items = generator.generate(type_id, 50, seed=9).items
        assert check_items(generator, type_id, items) == [], type_id
