from fakeverse.hierarchy import PlaceTree
from fakeverse.loader import load_file
from fakeverse.model import Patterns, Place
from support import TEST_WORLD


def tree() -> PlaceTree:
    universe = load_file(TEST_WORLD).universe
    assert universe is not None
    return PlaceTree(universe.places)


def test_chain_and_ancestors() -> None:
    places = tree()
    assert [p.id for p in places.chain("millbrook")] == ["millbrook", "amber-vale", "north-reach"]
    assert [p.id for p in places.chain("dunmere")] == ["dunmere", "south-march"]
    assert places.chain("unknown") == []
    assert places.ancestor_at("millbrook", "area") is not None
    assert places.ancestor_at("dunmere", "subdivision") is None


def test_localities_keep_file_order() -> None:
    places = tree()
    assert [p.id for p in places.localities_under("north-reach")] == [
        "millbrook",
        "stonebridge",
        "marshton",
    ]
    assert [p.id for p in places.localities_under("dunmere")] == ["dunmere"]
    assert [p.id for p in places.localities()][:2] == ["millbrook", "stonebridge"]


def test_nearest_override_wins() -> None:
    places = tree()
    universe_patterns = Patterns(postal_code="U-{digits:1}")
    assert places.resolve_pattern("stonebridge", "postal_code", universe_patterns) == (
        "SB-{digits:2}"
    )
    assert places.resolve_pattern("millbrook", "postal_code", universe_patterns) == (
        "NR-{digits:4}"
    )
    assert places.resolve_pattern("dunmere", "postal_code", universe_patterns) == "U-{digits:1}"
    assert places.resolve_pattern("dunmere", "postal_code", Patterns()) is None


def test_cycles_do_not_loop() -> None:
    cyclic = PlaceTree(
        [
            Place(id="a", level="subdivision", parent="b", name="A"),
            Place(id="b", level="subdivision", parent="a", name="B"),
        ]
    )
    assert [p.id for p in cyclic.chain("a")] == ["a", "b"]
