"""Every maintainer declared in a universe file owns it in .github/CODEOWNERS."""

from pathlib import Path

import pytest

from fakeverse.loader import find_universe_files, load_file

ROOT = Path(__file__).parents[2]
FILES = find_universe_files([ROOT / "universes"])


def owners() -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    for line in (ROOT / ".github" / "CODEOWNERS").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            pattern, *handles = line.split()
            rules[pattern] = handles
    return rules


def test_core_is_owned() -> None:
    rules = owners()
    for pattern in ("/src/", "/schema/", "/.github/"):
        assert rules.get(pattern), pattern


@pytest.mark.parametrize("path", FILES, ids=lambda path: path.stem)
def test_universe_maintainers_own_their_file(path: Path) -> None:
    universe = load_file(path).universe
    assert universe is not None
    handles = owners().get(f"/universes/{path.name}")
    assert handles is not None, f"No CODEOWNERS line for /universes/{path.name}"
    assert sorted(handles) == sorted(f"@{handle}" for handle in universe.universe.maintainers)
