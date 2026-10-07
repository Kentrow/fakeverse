import csv
import io
import json

import pytest

from fakeverse.errors import InvalidOption
from fakeverse.fakeverse import GenerationMeta, GenerationResult
from fakeverse.formats import OutputFormat, flatten, render

META = GenerationMeta("w", "person", 2, 1, False, "fr", 0, "0.1.0", 1)
PEOPLE = GenerationResult(
    [
        {"name": "Ann", "address": {"town": "Bree", "zip": None}},
        {"name": "Ben, Jr.", "address": {"town": "Line 1\nLine 2", "zip": "B-1"}},
    ],
    META,
)


def test_json() -> None:
    document = json.loads(render(PEOPLE, OutputFormat.JSON))
    assert document["data"] == PEOPLE.items
    assert document["meta"]["seed"] == 1
    assert set(document["meta"]) == {
        "universe",
        "type",
        "count",
        "seed",
        "seed_generated",
        "locale",
        "locale_fallbacks",
        "data_version",
        "engine_revision",
        "duplicates",
    }


def test_ndjson() -> None:
    lines = render(PEOPLE, OutputFormat.NDJSON).splitlines()
    assert [json.loads(line) for line in lines] == PEOPLE.items


def test_csv_flattens_and_quotes() -> None:
    text = render(PEOPLE, OutputFormat.CSV)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows == [
        ["name", "address.town", "address.zip"],
        ["Ann", "Bree", ""],
        ["Ben, Jr.", "Line 1\nLine 2", "B-1"],
    ]


def test_csv_atomic_values() -> None:
    result = GenerationResult(["Frodo", None, 3], META)
    assert render(result, OutputFormat.CSV).splitlines() == ["value", "Frodo", '""', "3"]


def test_flatten() -> None:
    assert flatten("x") == {"value": "x"}
    assert flatten({"a": {"b": {"c": 1}}, "d": 2}) == {"a.b.c": 1, "d": 2}


def test_explain_is_refused_in_csv() -> None:
    with pytest.raises(InvalidOption, match="CSV"):
        render(PEOPLE, OutputFormat.CSV, explain=True)
