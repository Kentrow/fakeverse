import shutil
from pathlib import Path

import pytest
from api_support import ClientFactory, FakeClock
from fastapi.testclient import TestClient

from fakeverse.api.app import create_app
from fakeverse.api.settings import Settings

ROOT = Path(__file__).parents[2]
TEST_WORLD = ROOT / "tests" / "fixtures" / "universes" / "test-world.yaml"
MINIMAL = ROOT / "tests" / "fixtures" / "valid" / "minimal.yaml"

RELEASES = """
[[releases]]
version = "0.0.5"
engine_revision = 0
date = 2026-01-01

[[releases]]
version = "0.0.9"
engine_revision = 1
date = 2026-02-01
"""


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Snapshots 0.0.9 (minimal only) and 0.1.0 (minimal and test-world); 0.0.5 is retired."""
    root = tmp_path_factory.mktemp("data")
    for version in ("0.0.5", "0.0.9", "0.1.0"):
        (root / version).mkdir()
        shutil.copy(MINIMAL, root / version)
    shutil.copy(TEST_WORLD, root / "0.1.0")
    (root / "not-a-version").mkdir()
    (root / "releases.toml").write_text(RELEASES)
    return root


@pytest.fixture
def make_client(data_dir: Path) -> ClientFactory:
    def make(clock: FakeClock | None = None, **overrides: object) -> TestClient:
        options: dict[str, object] = {"data_dir": data_dir, "rate_limit": "0", **overrides}
        settings = Settings.model_validate(options)
        return TestClient(create_app(settings, clock=clock))

    return make


@pytest.fixture
def client(make_client: ClientFactory) -> TestClient:
    return make_client()
