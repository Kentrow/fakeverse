from typing import Any

import pytest

from fakeverse import UniverseGenerator
from fakeverse.errors import InvalidTemplate, PoolExhausted

TEMPLATE = {
    "name": "person.full_name",
    "contact": {"email": "person.email", "town": "person.address.locality"},
    "employer": "organization.name",
    "colleague": "person#2.full_name",
}


def test_structure_and_key_order(world: UniverseGenerator) -> None:
    result = world.template(TEMPLATE, 3, seed=1)
    assert result.meta.type == "template"
    assert result.meta.count == 3
    for row in result.items:
        assert list(row) == ["name", "contact", "employer", "colleague"]
        assert list(row["contact"]) == ["email", "town"]


def test_leaves_share_their_instance(world: UniverseGenerator) -> None:
    template = {
        "person": "person.full_name",
        "first": "person.first_name",
        "alias": "first_name",
        "address": "person.address",
        "town": "person#1.address.locality",
    }
    for row in world.template(template, 30, seed=2).items:
        assert row["person"].startswith(row["first"])
        assert row["alias"] == row["first"]
        assert row["town"] == row["address"]["locality"]


def test_instances_are_independent_of_other_leaves(world: UniverseGenerator) -> None:
    # Guaranteed without uniqueness: with it, a row retried because it repeated a previous
    # row draws new instances.
    small = world.template({"a": "person.full_name"}, 10, seed=3, unique=False).items
    big = world.template(
        {"z": "organization.name", "a": "person.full_name", "b": "person#2.email"},
        10,
        seed=3,
        unique=False,
    ).items
    assert [row["a"] for row in big] == [row["a"] for row in small]


def test_numbered_instances_differ(world: UniverseGenerator) -> None:
    rows = world.template({"a": "person.full_name", "b": "person#2.full_name"}, 20, seed=4).items
    assert any(row["a"] != row["b"] for row in rows)


def test_extensions_and_explain(world_fr: UniverseGenerator) -> None:
    result = world_fr.template(
        {"barge": "barge.plate", "relic": {"name": "relic.name", "age": "relic.age"}},
        5,
        seed=5,
        explain=True,
    )
    for row in result.items:
        assert set(row["barge"]) == {"value", "origin", "locale", "fallback"}
        assert isinstance(row["relic"]["age"]["value"], int)


def test_template_is_deterministic_with_prefix_stability(world: UniverseGenerator) -> None:
    rows = world.template(TEMPLATE, 8, seed=6).items
    assert world.template(TEMPLATE, 3, seed=6).items == rows[:3]


def test_unique_rows(world: UniverseGenerator) -> None:
    rows = world.template({"r": "relic.name"}, 2, seed=1, unique=True).items
    assert {row["r"] for row in rows} == {"Ember Stone", "Glass Crown"}
    with pytest.raises(PoolExhausted):
        world.template({"r": "relic.name"}, 3, seed=1, unique=True)


def errors_of(generator: UniverseGenerator, template: Any, **options: Any) -> list[Any]:
    with pytest.raises(InvalidTemplate) as info:
        generator.template(template, seed=1, **options)
    assert info.value.slug == "invalid-template"
    return [(e["path"], e["reason"].split(";")[0]) for e in info.value.errors]


def test_every_error_is_reported_at_once(world: UniverseGenerator) -> None:
    template = {
        "a": "person.nickname",
        "b": "starship.name",
        "c": {"d": "first_name.value", "e": 3, "f": ["person.email"]},
        "g": "person",
        "h": "Person Name",
        "i": "person.full_name.first",
        "j": "barge.speed",
        "k": "person#0.full_name",
        "l~/": "person.address.planet",
        "m": {},
        "ok": "person.email",
    }
    assert errors_of(world, template) == [
        ("/a", "Unknown field 'nickname'"),
        ("/b", "Type 'starship' is not supported by this universe"),
        ("/c/d", "Atomic type 'first_name' has no field"),
        ("/c/e", "A leaf must be a path string or an object"),
        ("/c/f", "A leaf must be a path string or an object"),
        ("/g", "A field of 'person' is required"),
        ("/h", "Invalid path"),
        ("/i", "Field 'full_name' has no sub-field"),
        ("/j", "Unknown field"),
        ("/k", "Invalid path"),
        ("/l~0~1", "Unknown field 'planet'"),
        ("/m", "Empty object"),
    ]


def test_limits(world: UniverseGenerator) -> None:
    deep = {"a": {"b": {"c": {"d": "person.email"}}}}
    assert world.template(deep, seed=1).items
    deeper = {"a": {"b": {"c": {"d": {"e": "person.email"}}}}}
    assert errors_of(world, deeper) == [("/a/b/c/d", "Templates are limited to 4 levels")]
    wide = {f"k{i}": "first_name" for i in range(51)}
    assert errors_of(world, wide) == [("", "51 leaves")]
    assert world.template(wide, seed=1, max_leaves=60).items


@pytest.mark.parametrize("template", [{}, [], "person.email", None])
def test_not_an_object(world: UniverseGenerator, template: Any) -> None:
    assert errors_of(world, template) == [("", "Expected a non-empty object")]
