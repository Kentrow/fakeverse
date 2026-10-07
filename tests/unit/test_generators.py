from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml

from fakeverse import Fakeverse, UniverseGenerator
from fakeverse.errors import InvalidOption, TypeNotSupported
from fakeverse.types import COMPOSITES
from support import MINIMAL

VALEFOLK_LOCALITIES = {"Millbrook", "Stonebridge"}


def test_address_fields_and_hierarchy(world: UniverseGenerator) -> None:
    addresses = world.generate("address", 200, seed=1).items
    expected = {
        "Millbrook": ("Amber Vale", "North Reach"),
        "Stonebridge": ("Amber Vale", "North Reach"),
        "Marshton": ("Grey Fens", "North Reach"),
        "Copperfield": ("Red Hills", "South March"),
        "Dunmere": (None, "South March"),
        "Port Lumen": (None, "East Isles"),
    }
    for address in addresses:
        assert list(address) == [f.name for f in COMPOSITES["address"]]
        assert (address["subdivision"], address["area"]) == expected[address["locality"]]
    assert set(Counter(a["locality"] for a in addresses)) == set(expected)


def test_pattern_overrides_by_nearest_place(world: UniverseGenerator) -> None:
    for address in world.generate("address", 200, seed=2).items:
        locality = address["locality"]
        postal = address["postal_code"]
        if locality == "Stonebridge":
            assert postal.startswith("SB-")
            assert len(postal) == 5
        elif locality in {"Millbrook", "Marshton"}:
            assert postal.startswith("NR-")
        else:
            assert postal is None
        if locality in {"Millbrook", "Stonebridge"}:
            assert address["street_address"].endswith("Road")
        if locality == "Copperfield":
            assert address["formatted"].count(", ") == 3


def test_formatted_address_cleans_missing_postal_code(world: UniverseGenerator) -> None:
    for address in world.generate("address", 100, seed=3).items:
        if address["locality"] == "Dunmere":
            assert address["formatted"].split("\n") == [
                address["street_address"],
                "Dunmere",
                "South March",
            ]
            return
    pytest.fail("no address in Dunmere")


def test_person_coherence(world: UniverseGenerator) -> None:
    for person in world.generate("person", 200, seed=4).items:
        assert list(person) == [f.name for f in COMPOSITES["person"]]
        if person["people"] == "Valefolk":
            assert person["address"]["locality"] in VALEFOLK_LOCALITIES
            assert person["full_name"] == f"{person['first_name']} {person['last_name']}"
            assert person["gender"] in {"masculine", "feminine"}
        elif person["people"] == "Fenwalker":
            assert person["last_name"] is None
            assert person["gender"] is None
            assert person["full_name"] == person["first_name"]
            assert person["address"]["locality"] in {"Marshton", "Dunmere"}
            assert (
                person["email"] == f"{person['first_name'].lower()}@{person['email'].split('@')[1]}"
            )
        else:
            assert person["people"] == "Islander"
            assert person["full_name"].endswith(" of Port Lumen")
            assert person["phone"].startswith("+99 ")
        if person["people"] != "Islander":
            assert person["phone"].startswith("+10 ")


def test_person_options(world: UniverseGenerator) -> None:
    feminine = world.generate("person", 100, seed=5, gender="feminine").items
    assert {p["gender"] for p in feminine} == {"feminine"}
    # A people whose first names have no gender accepts any imposed gender.
    assert {p["people"] for p in feminine} == {"Valefolk", "Islander", "Fenwalker"}
    assert all(
        p["first_name"] in {"Reed", "Sedge", "Willow"}
        for p in feminine
        if p["people"] == "Fenwalker"
    )
    neutral = world.generate("first_name", 50, seed=5, gender="neutral").items
    assert set(neutral) <= {"Tide", "Shore", "Ivo", "Jory", "Reed", "Sedge", "Willow"}
    assert "Tide" in neutral
    fen = world.generate("person", 30, seed=5, people="fenwalker").items
    assert {p["people"] for p in fen} == {"Fenwalker"}


def test_impossible_options(world: UniverseGenerator, tmp_path: Path) -> None:
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    data["peoples"][0]["first_names"] = [{"value": "Ann", "gender": "feminine"}]
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    minimal = Fakeverse(tmp_path).universe("minimal")
    with pytest.raises(InvalidOption, match="No people matches"):
        minimal.generate("person", seed=1, people="folk", gender="masculine")
    with pytest.raises(InvalidOption, match="No people matches"):
        minimal.generate("first_name", seed=1, gender="neutral")
    with pytest.raises(InvalidOption, match="Unknown people"):
        world.generate("person", seed=1, people="dwarf")
    with pytest.raises(InvalidOption, match="Invalid gender"):
        world.generate("person", seed=1, gender="other")
    with pytest.raises(InvalidOption, match="only applies to person"):
        world.generate("address", seed=1, gender="feminine")
    with pytest.raises(InvalidOption, match="only applies to person"):
        world.generate("barge", seed=1, people="valefolk")


def test_last_name_alias_is_never_null(world: UniverseGenerator) -> None:
    assert None not in world.generate("last_name", 100, seed=6).items
    with pytest.raises(InvalidOption):
        world.generate("last_name", seed=1, people="fenwalker")


def test_atomic_aliases_are_projections(world: UniverseGenerator) -> None:
    emails = world.generate("email", 50, seed=7).items
    assert all("@" in email for email in emails)
    assert all(isinstance(v, str) for v in world.generate("organization_name", 20, seed=7).items)
    postal = world.generate("postal_code", 100, seed=7).items
    assert None in postal
    assert any(isinstance(code, str) for code in postal)


def test_organizations(world: UniverseGenerator) -> None:
    orgs = world.generate("organization", 400, seed=8).items
    canonical = [o for o in orgs if o["name"] in {"Copper Guild", "The Lantern"}]
    for org in canonical:
        expected = "Copperfield" if org["name"] == "Copper Guild" else "Port Lumen"
        assert org["address"]["locality"] == expected
        assert org["kind"] is not None
    generated = [o for o in orgs if o["name"].startswith("The ") and o["name"] != "The Lantern"]
    assert all(o["kind"] is None for o in generated)
    # Ratio 0.25: about a quarter of the organizations are generated.
    assert 60 < len(generated) < 140


def ratio_universe(tmp_path: Path, ratio: float) -> UniverseGenerator:
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    data["generation"] = {"organization_generated_ratio": ratio}
    data["patterns"]["organization_name"] = "Generated {vocab.street}"
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    return Fakeverse(tmp_path).universe("minimal")


@pytest.mark.parametrize(("ratio", "expected"), [(0, "Guild"), (1, "Generated Street")])
def test_organization_ratio_extremes(tmp_path: Path, ratio: float, expected: str) -> None:
    names = ratio_universe(tmp_path, ratio).generate("organization_name", 30, seed=1).items
    assert set(names) == {expected}


def test_extension_items(world_fr: UniverseGenerator) -> None:
    relics = world_fr.generate("relic", 100, seed=9).items
    assert {r["name"] for r in relics} == {"Pierre de braise", "Glass Crown"}
    for relic in relics:
        assert list(relic) == ["name", "kind", "age"]
        assert relic["age"] == (300 if relic["name"] == "Pierre de braise" else 12)


def test_extension_fields(world: UniverseGenerator) -> None:
    for barge in world.generate("barge", 100, seed=10).items:
        assert list(barge) == [
            "name",
            "registry",
            "cargo",
            "home_port",
            "region",
            "crew",
            "owner",
            "plate",
        ]
        assert barge["name"] in {"The OAK", "The MILL", "The BELL"}
        assert 2 <= barge["crew"] <= 40
        assert barge["plate"] == f"{barge['registry']} ({barge['crew']})"
        assert barge["region"] in {"North Reach", "South March", "East Isles"}
        assert barge["owner"] in {"Valefolk", "Fenwalker", "Islander"}


def test_unsupported_type(world: UniverseGenerator, tmp_path: Path) -> None:
    with pytest.raises(TypeNotSupported, match="does not support type 'starship'"):
        world.generate("starship", seed=1)
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    del data["patterns"]["email"]
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    minimal = Fakeverse(tmp_path).universe("minimal")
    with pytest.raises(TypeNotSupported):
        minimal.generate("email", seed=1)
    assert minimal.generate("person", seed=1).items[0]["email"] is None


def test_nullable_outputs_rendering_empty_are_null(tmp_path: Path) -> None:
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    del data["peoples"][0]["family_names"]
    data["patterns"]["email"] = "{family_name}"
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    person = Fakeverse(tmp_path).universe("minimal").one("person", seed=1)
    assert person["email"] is None


def test_template_alias_follows_its_composite(tmp_path: Path) -> None:
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    del data["peoples"][0]["family_names"]
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    minimal = Fakeverse(tmp_path).universe("minimal")
    row = minimal.template({"a": "last_name", "b": "person.last_name"}, seed=1).items[0]
    assert row == {"a": None, "b": None}
