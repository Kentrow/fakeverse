"""Colocation of template instances."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from fakeverse import Fakeverse, UniverseGenerator
from fakeverse.coherence import check_items
from fakeverse.errors import InvalidTemplate
from support import MINIMAL

TEMPLATE = {
    "who": "person.full_name",
    "home": "person.address",
    "org": "organization.name",
    "office": "organization.address",
    "other": "person#2.address.locality",
    "place": "address.locality",
}


def rows(generator: UniverseGenerator, colocate: Any, count: int = 120, seed: int = 1) -> Any:
    return generator.template(TEMPLATE, count, seed, colocate=colocate).items


def test_grouped_instances_share_their_locality(world: UniverseGenerator) -> None:
    for row in rows(world, [["person", "organization", "address"]]):
        assert row["home"]["locality"] == row["office"]["locality"] == row["place"]
        assert row["home"]["area"] == row["office"]["area"]


def test_ungrouped_instances_are_unchanged(world: UniverseGenerator) -> None:
    template = {"who": "person.full_name", "other": "person#2.full_name"}
    plain = world.template(template, 20, 5).items
    grouped = world.template(
        {**template, "org": "organization.name"}, 20, 5, colocate=[["person", "organization"]]
    ).items
    assert [row["other"] for row in grouped] == [row["other"] for row in plain]


def test_without_groups_nothing_changes(world: UniverseGenerator) -> None:
    template = {"who": "person.full_name", "org": "organization.name"}
    assert (
        world.template(template, 10, 2).items == world.template(template, 10, 2, colocate=[]).items
    )


def test_group_order_does_not_matter(world: UniverseGenerator) -> None:
    template = {"who": "person.full_name", "org": "organization.address.locality"}
    first = world.template(template, 10, 3, colocate=[["person", "organization"]]).items
    second = world.template(template, 10, 3, colocate=[["organization", "person#1"]]).items
    assert first == second


def test_grouped_people_live_in_their_homelands(world: UniverseGenerator) -> None:
    index = world.index
    homes = {
        world.label(info.people.name): {locality.place.id for locality in info.localities.items}
        for info in index.peoples
    }
    names = {info.place.id: world.label(info.place.name) for info in index.localities.items}
    template = {
        "people": "person.people",
        "town": "person.address.locality",
        "address": "person.address",
        "org": "organization.name",
        "office": "organization.address",
    }
    result = world.template(template, 150, 4, colocate=[["person", "organization"]]).items
    for row in result:
        allowed = {names[place_id] for place_id in homes[row["people"]]}
        assert row["town"] in allowed
        assert row["office"] == {**row["office"], "locality": row["town"]}
    assert check_items(world, "address", [row["address"] for row in result]) == []
    assert check_items(world, "address", [row["office"] for row in result]) == []
    # Canonical organizations stay in their places: The Lantern is only in Port Lumen.
    lantern = [row for row in result if row["org"] == "The Lantern"]
    assert lantern
    assert all(row["town"] == "Port Lumen" and row["people"] == "Islander" for row in lantern)


def test_deterministic_and_unique(world: UniverseGenerator) -> None:
    template = {"who": "person.full_name", "org": "organization.name"}
    groups = [["person", "organization"]]
    first = world.template(template, 30, 9, colocate=groups, unique=True)
    assert first == world.template(template, 30, 9, colocate=groups, unique=True)
    assert len({(row["who"], row["org"]) for row in first.items}) == 30


def errors(generator: UniverseGenerator, template: Any, colocate: Any) -> list[Any]:
    with pytest.raises(InvalidTemplate) as info:
        generator.template(template, seed=1, colocate=colocate)
    return [(error["path"], error["reason"]) for error in info.value.errors]


def test_invalid_groups(world: UniverseGenerator) -> None:
    template = {"a": "person.full_name", "b": "organization.name", "c": "barge.name"}
    assert errors(world, template, [["person"], ["barge", "person"], ["person#2", "address"]]) == [
        ("/colocate/0", "A group needs at least two instances"),
        ("/colocate/1/0", "Expected an instance of person, address, organization"),
        ("/colocate/2/0", "This instance is not used by the template"),
        ("/colocate/2/1", "This instance is not used by the template"),
    ]
    assert errors(world, template, [["person", "organization"], ["organization", "person"]]) == [
        ("/colocate/1/0", "An instance belongs to one group at most"),
        ("/colocate/1/1", "An instance belongs to one group at most"),
    ]
    assert errors(world, template, [[3, "person"]]) == [
        ("/colocate/0/0", "Expected an instance of person, address, organization")
    ]


def test_group_without_any_shared_locality(tmp_path: Path) -> None:
    data: dict[str, Any] = yaml.safe_load(MINIMAL.read_text())
    data["places"].append({"id": "isle", "level": "area", "name": "Isle"})
    data["places"].append({"id": "port", "level": "locality", "parent": "isle", "name": "Port"})
    data["organizations"][0]["places"] = ["port"]  # people live in county, guild is in port
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    minimal = Fakeverse(tmp_path).universe("minimal")
    template = {"a": "person.full_name", "b": "organization.name"}
    assert errors(minimal, template, [["person", "organization"]]) == [
        ("/colocate/0", "No locality can host all these instances")
    ]
    data["patterns"]["organization_name"] = "The {vocab.street}"
    (tmp_path / "minimal.yaml").write_text(yaml.safe_dump(data))
    generated = Fakeverse(tmp_path).universe("minimal")
    result = generated.template(template, 5, 1, colocate=[["person", "organization"]]).items
    assert {row["b"] for row in result} == {"The Street"}


def test_group_errors_come_with_template_errors(world: UniverseGenerator) -> None:
    template = {"x": 1, "p": "person.full_name", "o": "organization.name"}
    assert errors(world, template, [["person"], ["person", "starship"]]) == [
        ("/x", "A leaf must be a path string or an object"),
        ("/colocate/0", "A group needs at least two instances"),
        ("/colocate/1/1", "Expected an instance of person, address, organization"),
    ]
    # Groups that are well formed add no error when the template itself is invalid.
    assert errors(world, template, [["person", "organization"]]) == [
        ("/x", "A leaf must be a path string or an object")
    ]
