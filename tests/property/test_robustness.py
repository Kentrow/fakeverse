"""Robustness: validation never crashes, and a valid universe always generates coherent data.

Universe files come from contributors (and from pull requests of forks): whatever they
contain, validation must report issues rather than raise, and anything it accepts must be
safe for the engine.
"""

import copy
from pathlib import Path
from typing import Any

import yaml
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fakeverse.coherence import check_items
from fakeverse.engine.index import build_index
from fakeverse.errors import InvalidTemplate
from fakeverse.fakeverse import UniverseGenerator
from fakeverse.loader import load_file
from fakeverse.patterns import PatternSyntaxError, parse_pattern
from fakeverse.types import ATOMIC_ALIASES
from fakeverse.validation import validate_data
from support import MINIMAL, TEST_WORLD

PROFILE = settings(
    max_examples=150,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# Values that are likely to hit edge cases of the format.
INTERESTING = st.sampled_from(
    [
        "",
        " ",
        "x",
        "fr",
        "en",
        "de",
        "fr_FR",
        "area",
        "subdivision",
        "locality",
        "land",
        "county",
        "town",
        "folk",
        "street",
        "masculine",
        "feminine",
        "{first_name}",
        "{family_name}",
        "{subdivision}",
        "{postal_code}",
        "{locality}",
        "{vocab.street}",
        "{vocab.nope}",
        "{digits:3}",
        "{int:5-1}",
        "{",
        "}}",
        "{{x}}",
        " - ",
        "1-5",
        "a" * 81,
        0,
        1,
        -1,
        1001,
        0.25,
        0.3,
        True,
        False,
        None,
        [],
        {},
        {"en": "A"},
        {"fr": "B"},
        {"value": "V", "gender": "neutral"},
    ]
)

JSONISH = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=8), children, max_size=4)
    ),
    max_leaves=20,
)


def paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Every path of a data tree, in a deterministic order."""
    found = [prefix]
    if isinstance(node, dict):
        for key in node:
            found.extend(paths(node[key], (*prefix, key)))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(paths(item, (*prefix, index)))
    return found


def parent_of(data: Any, path: tuple[Any, ...]) -> Any:
    node = data
    for part in path[:-1]:
        node = node[part]
    return node


@st.composite
def mutated(draw: st.DrawFn, source: Path) -> Any:
    """A universe file with a few random mutations."""
    data = yaml.safe_load(source.read_text())
    for _ in range(draw(st.integers(1, 3))):
        candidates = [path for path in paths(data) if path]
        path = draw(st.sampled_from(candidates))
        parent = parent_of(data, path)
        action = draw(st.sampled_from(["replace", "delete", "duplicate"]))
        if action == "replace":
            parent[path[-1]] = copy.deepcopy(draw(INTERESTING | JSONISH))
        elif action == "delete":
            del parent[path[-1]]
        elif isinstance(parent, list):
            parent.append(copy.deepcopy(parent[path[-1]]))
    return data


def check_generation(data: Any) -> None:
    universe, issues = validate_data(data)
    assert all(issue.severity in ("error", "warning") for issue in issues)
    if universe is None:
        return
    index = build_index(universe)
    capabilities = index.capabilities
    types = [*capabilities.core, *(ext.id for ext in capabilities.extensions)]
    for locale in universe.universe.locales:
        generator = UniverseGenerator(index, locale, "0.0.0")
        for type_id in types:
            items = generator.generate(type_id, 3, seed=7).items
            assert check_items(generator, type_id, items) == [], (type_id, locale)
        if "person" in capabilities.core and "organization" in capabilities.core:
            template = {"a": "person.address.locality", "b": "organization.address.locality"}
            try:
                rows = generator.template(template, 3, 2, colocate=[["person", "organization"]])
            except InvalidTemplate:
                pass  # no locality hosts both: refused before any generation
            else:
                assert all(row["a"] == row["b"] for row in rows.items)
        aliases = [type_id for type_id in capabilities.core if type_id in ATOMIC_ALIASES]
        if aliases:
            rows = generator.template({alias: alias for alias in aliases}, 2, 1).items
            assert all(list(row) == aliases for row in rows)


@PROFILE
@given(data=JSONISH)
def test_arbitrary_data_never_crashes_validation(data: Any) -> None:
    validate_data(data)


@PROFILE
@given(data=mutated(MINIMAL))
def test_valid_mutations_of_minimal_generate_coherent_data(data: Any) -> None:
    check_generation(data)


@PROFILE
@given(data=mutated(TEST_WORLD))
def test_valid_mutations_of_test_world_generate_coherent_data(data: Any) -> None:
    check_generation(data)


@PROFILE
@given(source=st.text(max_size=40))
def test_pattern_parser_only_raises_syntax_errors(source: str) -> None:
    try:
        pattern = parse_pattern(source)
    except PatternSyntaxError:
        return
    assert pattern.source == source


@settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(content=st.binary(max_size=200) | st.text(max_size=200).map(str.encode))
def test_load_file_never_raises(content: bytes, tmp_path_factory: Any) -> None:
    path = tmp_path_factory.mktemp("fuzz") / "fuzz.yaml"
    path.write_bytes(content)
    load_file(path)
