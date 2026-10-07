import csv
import io
import json
from typing import Any

import pytest
from api_support import ClientFactory
from fastapi.testclient import TestClient

from fakeverse import Fakeverse

BASE = "/v1/universes/test-world/generate"
PERSON = f"{BASE}/person"


def test_json_matches_the_package(client: TestClient, data_dir: Any) -> None:
    response = client.get(PERSON, params={"count": 3, "seed": 42, "locale": "fr"})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    body = response.json()
    expected = Fakeverse(data_dir / "0.1.0").universe("test-world", "fr").generate("person", 3, 42)
    assert body["data"] == expected.items
    assert body["meta"] == {**expected.meta.to_dict(), "data_version": "0.1.0"}


def test_common_headers(client: TestClient) -> None:
    for fmt in ("json", "ndjson", "csv"):
        response = client.get(PERSON, params={"seed": 7, "locale": "fr", "format": fmt})
        assert response.headers["Fakeverse-Seed"] == "7"
        assert response.headers["Fakeverse-Data-Version"] == "0.1.0"
        assert response.headers["Fakeverse-Engine-Revision"] == "1"
        assert response.headers["Fakeverse-Locale"] == "fr"
        assert response.headers["Fakeverse-Locale-Fallbacks"].isdigit()


def test_seed_generated(client: TestClient) -> None:
    body = client.get(PERSON).json()
    assert body["meta"]["seed_generated"] is True
    assert client.get(PERSON).headers["Cache-Control"] == "no-store"


def test_ndjson(client: TestClient) -> None:
    response = client.get(PERSON, params={"count": 4, "seed": 1, "format": "ndjson"})
    assert response.headers["content-type"] == "application/x-ndjson"
    lines = [json.loads(line) for line in response.text.splitlines()]
    assert len(lines) == 4
    assert lines[0]["address"]["locality"]


def test_csv(client: TestClient) -> None:
    response = client.get(PERSON, params={"count": 2, "seed": 1, "format": "csv"})
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    rows = list(csv.reader(io.StringIO(response.text)))
    assert "address.locality" in rows[0]
    assert len(rows) == 3
    atomic = client.get(
        "/v1/universes/test-world/generate/postal_code",
        params={"count": 30, "seed": 1, "format": "csv"},
    )
    lines = atomic.text.splitlines()
    assert lines[0] == "value"
    assert '""' in lines


@pytest.mark.parametrize(
    ("accept", "media_type"),
    [
        ("application/x-ndjson", "application/x-ndjson"),
        ("text/csv;q=0.9, application/json", "text/csv; charset=utf-8"),
        ("text/html, */*", "application/json"),
        ("", "application/json"),
    ],
)
def test_accept_header(client: TestClient, accept: str, media_type: str) -> None:
    response = client.get(PERSON, params={"seed": 1}, headers={"Accept": accept})
    assert response.headers["content-type"] == media_type


def test_format_parameter_wins_over_accept(client: TestClient) -> None:
    response = client.get(
        PERSON, params={"seed": 1, "format": "json"}, headers={"Accept": "text/csv"}
    )
    assert response.headers["content-type"] == "application/json"


def test_options(client: TestClient) -> None:
    body = client.get(
        PERSON,
        params={
            "count": 20,
            "seed": 3,
            "gender": "feminine",
            "people": "valefolk",
            "unique": "true",
        },
    ).json()
    assert {p["gender"] for p in body["data"]} == {"feminine"}
    assert {p["people"] for p in body["data"]} == {"Valefolk"}
    explained = client.get(PERSON, params={"seed": 3, "explain": "true"}).json()
    assert set(explained["data"][0]["first_name"]) == {"value", "origin", "locale", "fallback"}


def test_extension_type(client: TestClient) -> None:
    body = client.get("/v1/universes/test-world/generate/barge", params={"seed": 2}).json()
    assert body["meta"]["type"] == "barge"


def test_data_version(client: TestClient) -> None:
    old = client.get(
        "/v1/universes/minimal/generate/first_name", params={"seed": 1, "data_version": "0.0.9"}
    )
    assert old.status_code == 200
    assert old.json()["meta"]["data_version"] == "0.0.9"
    missing = client.get(
        "/v1/universes/test-world/generate/person", params={"data_version": "0.0.9"}
    )
    assert missing.status_code == 404
    assert missing.json()["type"] == "/problems/universe-not-found"


def problem(response: Any) -> tuple[int, str]:
    assert response.headers["content-type"] == "application/problem+json"
    return response.status_code, response.json()["type"].removeprefix("/problems/")


@pytest.mark.parametrize(
    ("path", "params", "expected"),
    [
        (PERSON, {"count": 1001}, (422, "count-too-large")),
        (PERSON, {"count": 0}, (422, "invalid-parameter")),
        (PERSON, {"count": "many"}, (422, "invalid-parameter")),
        (PERSON, {"seed": -1}, (422, "invalid-parameter")),
        (PERSON, {"seed": 2**63}, (422, "invalid-parameter")),
        (PERSON, {"gender": "other"}, (422, "invalid-parameter")),
        (PERSON, {"people": "dwarf"}, (422, "invalid-parameter")),
        (PERSON, {"format": "xml"}, (422, "invalid-parameter")),
        (PERSON, {"explain": "true", "format": "csv"}, (422, "invalid-parameter")),
        (PERSON, {"colour": "red"}, (422, "invalid-parameter")),
        (PERSON, {"locale": "de"}, (422, "locale-not-supported")),
        (PERSON, {"locale": "french"}, (422, "invalid-parameter")),
        (PERSON, {"data_version": "9.9.9"}, (404, "data-version-not-found")),
        (PERSON, {"data_version": "0.0.5"}, (410, "data-version-retired")),
        (f"{BASE}/address", {"gender": "feminine"}, (422, "invalid-parameter")),
        (f"{BASE}/starship", {}, (404, "type-not-supported")),
        ("/v1/universes/nope/generate/person", {}, (404, "universe-not-found")),
        (f"{BASE}/relic", {"count": 3, "unique": "true", "seed": 1}, (422, "pool-exhausted")),
    ],
)  # fmt: skip
def test_errors(client: TestClient, path: str, params: dict[str, Any], expected: Any) -> None:
    assert problem(client.get(path, params=params)) == expected


def test_error_details(client: TestClient) -> None:
    unsupported = client.get("/v1/universes/test-world/generate/starship").json()
    assert "barge" in unsupported["supported_types"]
    locale = client.get(PERSON, params={"locale": "de"}).json()
    assert locale["supported_locales"] == ["en", "fr"]
    exhausted = client.get(
        "/v1/universes/test-world/generate/relic", params={"count": 3, "unique": "true", "seed": 1}
    ).json()
    assert exhausted["unique_count"] == 2
    too_many = client.get(PERSON, params={"count": 5000}).json()
    assert too_many["max_count"] == 1000
    retired = client.get(PERSON, params={"data_version": "0.0.5"}).json()
    assert "pip install fakeverse==0.0.5" in retired["detail"]
    invalid = client.get(PERSON, params={"count": 0, "seed": "x"}).json()
    assert {e["name"] for e in invalid["errors"]} == {"count", "seed"}


def test_max_count_setting(make_client: ClientFactory) -> None:
    client = make_client(max_count=5)
    assert client.get(PERSON, params={"count": 5}).status_code == 200
    assert problem(client.get(PERSON, params={"count": 6})) == (422, "count-too-large")
    assert client.get("/v1/meta").json()["limits"]["max_count"] == 5


def test_uniqueness_modes(client: TestClient) -> None:
    url = f"{BASE}/relic"
    best = client.get(url, params={"count": 5, "seed": 1})
    assert best.status_code == 200
    assert best.json()["meta"]["duplicates"] == 3
    assert best.headers["Fakeverse-Duplicates"] == "3"
    strict = client.get(url, params={"count": 5, "seed": 1, "unique": "true"})
    assert problem(strict) == (422, "pool-exhausted")
    off = client.get(url, params={"count": 5, "seed": 1, "unique": "false"})
    assert off.json()["meta"]["duplicates"] == 3
