"""Quality bar of the universes shipped in universes/."""

from pathlib import Path

import pytest

from fakeverse.loader import find_universe_files, load_file
from fakeverse.validation import locale_coverage

UNIVERSES = Path(__file__).parents[2] / "universes"
FILES = find_universe_files([UNIVERSES])


def test_there_are_universes() -> None:
    assert [path.stem for path in FILES] == ["lotr", "starwars"]


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_valid_in_strict_mode(path: Path) -> None:
    result = load_file(path)
    assert result.issues == [], [issue.format() for issue in result.issues]


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_full_translation_coverage(path: Path) -> None:
    universe = load_file(path).universe
    assert universe is not None
    for locale, (ratio, missing) in locale_coverage(universe).items():
        assert ratio == 1.0, (locale, missing)


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_volume(path: Path) -> None:
    universe = load_file(path).universe
    assert universe is not None
    levels = [place.level for place in universe.places]
    assert levels.count("area") >= 4
    assert levels.count("subdivision") >= 10
    assert levels.count("locality") >= 30
    assert len(universe.peoples) >= 4
    assert sum(len(people.first_names) >= 30 for people in universe.peoples) >= 4
