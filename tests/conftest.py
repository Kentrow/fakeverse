import pytest
import yaml

from fakeverse import Fakeverse, UniverseGenerator
from support import FIXTURES, MINIMAL


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-goldens",
        action="store_true",
        default=False,
        help="Rewrite the golden files of tests/golden/ from the current engine output.",
    )


@pytest.fixture
def minimal_data() -> dict[str, object]:
    """Parsed data of the minimal valid universe, safe to mutate."""
    data: dict[str, object] = yaml.safe_load(MINIMAL.read_text(encoding="utf-8"))
    return data


@pytest.fixture(scope="session")
def fv() -> Fakeverse:
    """Fakeverse loaded with the fixture universes (test-world)."""
    return Fakeverse(FIXTURES / "universes")


@pytest.fixture(scope="session")
def world(fv: Fakeverse) -> UniverseGenerator:
    """Generator of test-world in English."""
    return fv.universe("test-world", "en")


@pytest.fixture(scope="session")
def world_fr(fv: Fakeverse) -> UniverseGenerator:
    """Generator of test-world in French."""
    return fv.universe("test-world", "fr")
