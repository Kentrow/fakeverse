"""Determinism, uniqueness, explain mode, origins and locale fallbacks."""

import time
from typing import Any

import pytest

from fakeverse import ENGINE_REVISION, Fakeverse, UniverseGenerator, __version__
from fakeverse.errors import InvalidOption, LocaleNotSupported, PoolExhausted, UniverseNotFound
from fakeverse.rng import MAX_SEED


def test_same_inputs_same_output(world: UniverseGenerator) -> None:
    first = world.generate("person", 5, seed=42)
    assert world.generate("person", 5, seed=42) == first
    assert world.generate("person", 5, seed=43).items != first.items


def test_prefix_stability(world: UniverseGenerator) -> None:
    long = world.generate("person", 20, seed=1).items
    assert world.generate("person", 7, seed=1).items == long[:7]


def test_unique_prefix_stability(world: UniverseGenerator) -> None:
    long = world.generate("first_name", 15, seed=1, unique=True).items
    assert len(set(long)) == 15
    assert world.generate("first_name", 6, seed=1, unique=True).items == long[:6]


def test_kind_and_options_change_the_seed(world: UniverseGenerator) -> None:
    persons = [p["first_name"] for p in world.generate("person", 10, seed=3).items]
    assert world.generate("first_name", 10, seed=3).items != persons
    default = world.generate("first_name", 10, seed=3).items
    # Strict and best effort give the same items while the pool is large enough.
    assert world.generate("first_name", 10, seed=3, unique=True).items == default
    assert world.generate("first_name", 10, seed=3, unique=False).items != default
    assert world.generate("first_name", 10, seed=3, gender="feminine").items != default


def test_pool_exhausted(world: UniverseGenerator) -> None:
    assert len(world.generate("relic", 2, seed=1, unique=True).items) == 2
    with pytest.raises(PoolExhausted) as info:
        world.generate("relic", 3, seed=1, unique=True)
    assert info.value.unique_count == 2
    assert info.value.slug == "pool-exhausted"


def test_meta(world_fr: UniverseGenerator) -> None:
    result = world_fr.generate("person", 3, seed=11)
    meta = result.meta
    assert (meta.universe, meta.type, meta.count, meta.seed) == ("test-world", "person", 3, 11)
    assert not meta.seed_generated
    assert (meta.locale, meta.data_version, meta.engine_revision) == (
        "fr",
        __version__,
        ENGINE_REVISION,
    )


def test_missing_seed_is_drawn_and_returned(world: UniverseGenerator) -> None:
    result = world.generate("first_name", 3)
    assert result.meta.seed_generated
    assert 0 <= result.meta.seed <= MAX_SEED
    assert world.generate("first_name", 3, result.meta.seed).items == result.items


@pytest.mark.parametrize("seed", [-1, MAX_SEED + 1, True, "1"])
def test_invalid_seed(world: UniverseGenerator, seed: Any) -> None:
    with pytest.raises(InvalidOption, match="seed"):
        world.generate("first_name", 1, seed)


@pytest.mark.parametrize("count", [0, -3, True, 1.5])
def test_invalid_count(world: UniverseGenerator, count: Any) -> None:
    with pytest.raises(InvalidOption, match="count"):
        world.generate("first_name", count, 1)


def test_one(world: UniverseGenerator) -> None:
    assert world.one("first_name", seed=5) == world.generate("first_name", 1, 5).items[0]
    assert world.one("first_name", seed=5, gender="feminine") in {
        "Elna", "Flora", "Greta", "Hilde", "Ivo", "Jory", "Reed", "Sedge", "Willow",
        "Marin", "Coral", "Shore",
    }  # fmt: skip


def explained(generator: UniverseGenerator, type_id: str, seed: int, **options: Any) -> Any:
    return generator.generate(type_id, 1, seed, explain=True, **options).items[0]


def test_explain_shape_and_origins(world: UniverseGenerator) -> None:
    for seed in range(40):
        person = explained(world, "person", seed)
        first = person["first_name"]
        assert set(first) == {"value", "origin", "locale", "fallback"}
        assert person["email"]["origin"] == "generated"
        assert person["address"]["street_address"]["origin"] == "generated"
        if person["people"]["value"] == "Fenwalker":
            assert person["full_name"]["origin"] == first["origin"]
            assert person["last_name"] == {
                "value": None,
                "origin": None,
                "locale": None,
                "fallback": False,
            }
        if first["value"] in {"Dorian", "Hilde", "Willow"}:
            assert first["origin"] == "generated"
        if first["value"] == "Aldo":
            assert first["origin"] == "canon"


def test_explain_does_not_change_values(world: UniverseGenerator) -> None:
    raw = world.generate("person", 3, seed=8).items
    rich = world.generate("person", 3, seed=8, explain=True).items
    assert [p["full_name"]["value"] for p in rich] == [p["full_name"] for p in raw]


def test_place_origin_follows_canon_flag(world: UniverseGenerator) -> None:
    for seed in range(60):
        address = explained(world, "address", seed)
        origin = address["locality"]["origin"]
        assert origin == ("generated" if address["locality"]["value"] == "Marshton" else "canon")


def test_fallbacks_are_counted(world_fr: UniverseGenerator, world: UniverseGenerator) -> None:
    assert world.generate("address", 50, seed=1).meta.locale_fallbacks == 0
    result = world_fr.generate("address", 50, seed=1, explain=True)
    fallback = [a for a in result.items if a["subdivision"]["fallback"]]
    assert all(a["subdivision"]["value"] == "Grey Fens" for a in fallback)
    assert all(a["subdivision"]["locale"] == "en" for a in fallback)
    assert all(a["formatted"]["fallback"] for a in fallback)
    expected = sum(leaf["fallback"] for address in result.items for leaf in address.values())
    assert result.meta.locale_fallbacks == expected > 0


def test_regional_locale_does_not_count(fv: Fakeverse) -> None:
    canada = fv.universe("test-world", "fr_CA")
    assert canada.locale == "fr-CA"
    names = canada.generate("locality", 50, seed=2).items
    assert "Moulinet" in names


def test_universe_lookup_errors(fv: Fakeverse) -> None:
    with pytest.raises(UniverseNotFound, match="Available: test-world"):
        fv.universe("lotr")
    with pytest.raises(LocaleNotSupported, match="Supported: en, fr"):
        fv.universe("test-world", "de")
    with pytest.raises(InvalidOption, match="Invalid locale"):
        fv.universe("test-world", "french")


def test_universes_listing(fv: Fakeverse) -> None:
    (info,) = fv.universes()
    assert (info.id, info.name, info.locales, info.default_locale) == (
        "test-world",
        "Test World",
        ("en", "fr"),
        "en",
    )
    assert fv.universes("fr_FR")[0].name == "Monde de test"
    assert fv.data_version == __version__


def test_generator_helpers(world_fr: UniverseGenerator) -> None:
    assert world_fr.id == "test-world"
    assert world_fr.label({"en": "Relic", "fr": "Relique"}) == "Relique"
    assert world_fr.capabilities().supports("barge")


def test_embedded_universes_load() -> None:
    assert [info.id for info in Fakeverse().universes()] == ["lotr", "starwars"]


def test_uniqueness_modes(world: UniverseGenerator) -> None:
    # test-world has two relics.
    best = world.generate("relic", 5, seed=1)
    names = [relic["name"] for relic in best.items]
    assert len(set(names[:2])) == 2
    assert best.meta.duplicates == 3
    with pytest.raises(PoolExhausted):
        world.generate("relic", 5, seed=1, unique=True)
    assert world.generate("relic", 2, seed=1, unique=True).items == best.items[:2]
    off = world.generate("relic", 5, seed=1, unique=False)
    assert off.meta.duplicates == 3
    assert world.generate("first_name", 5, seed=1).meta.duplicates == 0


def test_best_effort_stops_trying_once_exhausted(world: UniverseGenerator) -> None:
    start = time.perf_counter()
    result = world.generate("relic", 1000, seed=2)
    assert time.perf_counter() - start < 2
    assert result.meta.duplicates == 998


def test_best_effort_prefix_stability(world: UniverseGenerator) -> None:
    long = world.generate("area", 12, seed=4).items
    assert world.generate("area", 5, seed=4).items == long[:5]
