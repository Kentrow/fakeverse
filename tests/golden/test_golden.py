"""Golden tests: reference outputs of the engine on the test-world fixture.

They detect any change of the generation output. When one fails on purpose, bump
ENGINE_REVISION, note it in CHANGELOG.md, and regenerate with ``pytest --update-goldens``.
Goldens rely on the fixture, not on the real universes: editing universes/*.yaml never
breaks them.
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from fakeverse import Fakeverse, GenerationResult
from fakeverse.types import ATOMIC_ALIASES

GOLDEN_DIR = Path(__file__).parent
MESSAGE = (
    "Engine output changed: bump ENGINE_REVISION and regenerate goldens with "
    "`pytest --update-goldens`"
)

TEMPLATE = {
    "name": "person.full_name",
    "contact": {"email": "person.email", "town": "person.address.locality"},
    "employer": "organization.name",
    "colleague": "person#2.first_name",
    "barge": {"plate": "barge.plate", "home": "barge.home_port"},
}

type Case = Callable[[Fakeverse], Any]


def snapshot(result: GenerationResult) -> dict[str, Any]:
    """Items and metadata, without ``data_version``: a release must not break goldens."""
    meta = {key: value for key, value in result.meta.to_dict().items() if key != "data_version"}
    return {"data": result.items, "meta": meta}


def generate(locale: str, type_id: str, count: int, seed: int, **options: Any) -> Case:
    def run(fv: Fakeverse) -> Any:
        return snapshot(fv.universe("test-world", locale).generate(type_id, count, seed, **options))

    return run


def aliases(locale: str, seed: int) -> Case:
    def run(fv: Fakeverse) -> Any:
        generator = fv.universe("test-world", locale)
        return {alias: generator.generate(alias, 4, seed).items for alias in ATOMIC_ALIASES}

    return run


def template(locale: str, seed: int, **options: Any) -> Case:
    def run(fv: Fakeverse) -> Any:
        return snapshot(fv.universe("test-world", locale).template(TEMPLATE, 4, seed, **options))

    return run


CASES: dict[str, Case] = {
    "person-en-42": generate("en", "person", 5, 42),
    "person-fr-42": generate("fr", "person", 5, 42),
    "person-fr-7-explain": generate("fr", "person", 2, 7, explain=True),
    "person-en-9-options": generate("en", "person", 4, 9, gender="feminine", unique=True),
    "person-fr-3-people": generate("fr", "person", 3, 3, people="islander"),
    "address-fr-1": generate("fr", "address", 6, 1),
    "organization-en-5": generate("en", "organization", 8, 5),
    "organization-fr-5-explain": generate("fr", "organization", 2, 5, explain=True),
    "aliases-en-11": aliases("en", 11),
    "aliases-fr-11": aliases("fr", 11),
    "first-name-en-2-unique": generate("en", "first_name", 12, 2, unique=True),
    "relic-fr-4": generate("fr", "relic", 4, 4),
    "barge-en-6": generate("en", "barge", 4, 6),
    "barge-fr-6-explain": generate("fr", "barge", 1, 6, explain=True),
    "template-fr-8": template("fr", 8),
    "template-en-8-explain": template("en", 8, explain=True, unique=True),
}


def test_every_golden_file_has_a_case() -> None:
    assert {path.stem for path in GOLDEN_DIR.glob("*.json")} <= set(CASES)


@pytest.mark.parametrize("name", list(CASES))
def test_golden(name: str, fv: Fakeverse, request: pytest.FixtureRequest) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    actual = CASES[name](fv)
    if request.config.getoption("--update-goldens"):
        path.write_text(json.dumps(actual, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    assert path.exists(), f"Missing golden {path.name}: run `pytest --update-goldens`"
    expected = json.loads(path.read_text(encoding="utf-8"))
    assert actual == expected, MESSAGE
