"""Paths shared by the tests."""

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
TEST_WORLD = FIXTURES / "universes" / "test-world.yaml"
MINIMAL = FIXTURES / "valid" / "minimal.yaml"
INVALID = FIXTURES / "invalid"
