"""Stability of fakeverse.rng: expected values are hard-coded on purpose.

If one of these tests fails, the output of every generation changes: bump ENGINE_REVISION.
"""

import pytest

from fakeverse.rng import MAX_SEED, Rng, canonical_json, derive_seed, random_seed


def test_primitives_are_stable() -> None:
    rng = Rng(42)
    assert [rng.below(10) for _ in range(8)] == [1, 0, 4, 3, 3, 2, 1, 8]
    assert [rng.int_between(5, 9) for _ in range(5)] == [5, 9, 8, 5, 5]
    assert [rng.weighted_index((1, 4, 10)) for _ in range(8)] == [1, 1, 1, 2, 2, 0, 2, 1]
    assert rng.digits(6) == "863794"
    assert rng.letters(6) == "ZAYZFW"
    assert rng.below(1) == 0
    assert rng.below(2**70) == 319871163510331307281


def test_derive_seed_is_stable() -> None:
    assert derive_seed(1, "lotr", "person", "fr", {}, 42, 0) == (
        217030100297238331880755786274856520756
    )
    seed = derive_seed(
        1, "test-world", "first_name", "en", {"gender": "feminine", "unique": True}, 0, 3, 1
    )
    assert hex(seed) == "0xbf13590e8d87a2a18ea9e9c9fbc86c8c"


def test_derive_seed_ignores_mapping_order() -> None:
    assert derive_seed({"a": 1, "b": 2}) == derive_seed({"b": 2, "a": 1})
    assert derive_seed(1, 2) != derive_seed(2, 1)


def test_canonical_json() -> None:
    assert canonical_json({"b": 1, "a": ["é", None]}) == '{"a":["é",null],"b":1}'.encode()


def test_below_is_uniform_enough() -> None:
    rng = Rng(0)
    counts = [0] * 6
    for _ in range(6000):
        counts[rng.below(6)] += 1
    assert all(900 < count < 1100 for count in counts)


def test_weighted_index_respects_weights() -> None:
    rng = Rng(1)
    hits = [0, 0]
    for _ in range(4000):
        hits[rng.weighted_index((1, 4))] += 1
    assert 800 < hits[0] < 1200


def test_invalid_arguments() -> None:
    rng = Rng(0)
    with pytest.raises(ValueError, match="positive"):
        rng.below(0)
    with pytest.raises(ValueError, match="exceed"):
        rng.int_between(3, 2)


def test_random_seed_range() -> None:
    seeds = [random_seed() for _ in range(50)]
    assert all(0 <= seed <= MAX_SEED for seed in seeds)
    assert len(set(seeds)) > 1
