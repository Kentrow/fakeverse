"""Property tests: the coherence invariants hold for any seed.

Runs on every universe of universes/ and on the test-world fixture, for each locale and each
supported type.
"""

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fakeverse import Fakeverse, UniverseGenerator
from fakeverse.coherence import check_items
from fakeverse.rng import MAX_SEED

ROOT = Path(__file__).parents[2]
SOURCES = [ROOT / "universes", ROOT / "tests" / "fixtures" / "universes"]


def generators() -> list[tuple[UniverseGenerator, str]]:
    cases = []
    for directory in SOURCES:
        fakeverse = Fakeverse(directory)
        for info in fakeverse.universes():
            for locale in info.locales:
                generator = fakeverse.universe(info.id, locale)
                capabilities = generator.capabilities()
                types = [*capabilities.core, *(ext.id for ext in capabilities.extensions)]
                cases.extend((generator, type_id) for type_id in types)
    return cases


CASES = generators()


@pytest.mark.parametrize(
    ("generator", "type_id"),
    CASES,
    ids=[f"{g.id}-{g.locale}-{t}" for g, t in CASES],
)
@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(min_value=0, max_value=MAX_SEED))
def test_invariants_hold(generator: UniverseGenerator, type_id: str, seed: int) -> None:
    items = generator.generate(type_id, 5, seed).items
    assert check_items(generator, type_id, items) == []
    assert generator.generate(type_id, 5, seed).items == items
