import json
from typing import Any

import pytest
from api_support import ClientFactory
from fastapi.testclient import TestClient

URL = "/v1/universes/test-world/generate"
TEMPLATE = {"name": "person.full_name", "town": "person.address.locality"}


def test_template(client: TestClient) -> None:
    response = client.post(URL, json={"template": TEMPLATE, "count": 3, "seed": 4, "locale": "fr"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["type"] == "template"
    assert len(body["data"]) == 3
    assert list(body["data"][0]) == ["name", "town"]
    assert response.headers["Fakeverse-Seed"] == "4"


def test_template_formats(client: TestClient) -> None:
    ndjson = client.post(URL, json={"template": TEMPLATE, "count": 2, "format": "ndjson"})
    assert len(ndjson.text.splitlines()) == 2
    csv = client.post(URL, json={"template": TEMPLATE, "seed": 1}, headers={"Accept": "text/csv"})
    assert csv.text.splitlines()[0] == "name,town"


def test_invalid_template_lists_every_path(client: TestClient) -> None:
    response = client.post(URL, json={"template": {"a": "person.nope", "b": {"c": "starship.x"}}})
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problems/invalid-template"
    assert [e["path"] for e in body["errors"]] == ["/a", "/b/c"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"template": "person.email"},
        {"template": TEMPLATE, "gender": "feminine"},
        {"template": TEMPLATE, "count": 0},
        {"template": TEMPLATE, "seed": "1"},
        {"template": TEMPLATE, "format": "xml"},
        {"template": TEMPLATE, "explain": True, "format": "csv"},
        [1, 2],
    ],
)
def test_invalid_bodies(client: TestClient, body: Any) -> None:
    response = client.post(URL, json=body)
    assert response.status_code == 422
    assert response.json()["type"] == "/problems/invalid-parameter"


def test_invalid_json(client: TestClient) -> None:
    response = client.post(URL, content=b"{nope", headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["errors"][0]["message"].startswith("Invalid JSON")


def test_payload_too_large(client: TestClient) -> None:
    big = {"template": TEMPLATE, "padding": "x" * (64 * 1024)}
    response = client.post(URL, content=json.dumps(big).encode())
    assert response.status_code == 413
    assert response.json()["type"] == "/problems/payload-too-large"


def test_body_without_content_length_is_still_limited(client: TestClient) -> None:
    def chunks() -> Any:
        yield b'{"template": {"a": "first_name"}, "x": "'
        yield b"x" * (64 * 1024)
        yield b'"}'

    response = client.post(URL, content=chunks())
    assert response.status_code == 413


def test_template_errors(client: TestClient) -> None:
    assert client.post(URL, json={"template": TEMPLATE, "count": 1001}).status_code == 422
    locale = client.post(URL, json={"template": TEMPLATE, "locale": "de"})
    assert locale.json()["type"] == "/problems/locale-not-supported"
    retired = client.post(URL, json={"template": TEMPLATE, "data_version": "0.0.5"})
    assert retired.status_code == 410
    exhausted = client.post(
        URL, json={"template": {"r": "relic.name"}, "count": 3, "unique": True, "seed": 1}
    )
    assert exhausted.json()["unique_count"] == 2
    unknown = client.post(URL, params={"x": "1"}, json={"template": TEMPLATE})
    assert unknown.status_code == 422


def test_max_template_leaves_setting(make_client: ClientFactory) -> None:
    client = make_client(max_template_leaves=1)
    response = client.post(URL, json={"template": TEMPLATE})
    assert response.status_code == 422
    assert response.json()["errors"][0]["reason"] == "2 leaves; the maximum is 1"
    assert client.get("/v1/meta").json()["limits"]["max_template_leaves"] == 1


def test_deeply_nested_json(client: TestClient) -> None:
    response = client.post(URL, content=b"[" * 20000, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    # Python 3.12 and 3.13 hit the recursion limit; 3.14 parses iteratively and fails at the end.
    assert response.json()["errors"][0]["message"].startswith("Invalid JSON")


def test_template_work_budget(make_client: ClientFactory) -> None:
    client = make_client(max_count=10)
    template = {f"p{n}": f"person#{n}.full_name" for n in range(1, 7)}
    assert client.post(URL, json={"template": template, "count": 8}).status_code == 200
    response = client.post(URL, json={"template": template, "count": 9})
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problems/count-too-large"
    assert body["max_instances"] == 50


@pytest.mark.parametrize(
    "body",
    [
        b'{"template": {"a": NaN}}',
        b'{"template": {"a": "first_name"}, "count": Infinity}',
        b'{"template": {"a": ' + b"1" * 5000 + b"}}",
    ],
)
def test_non_standard_json_is_refused(client: TestClient, body: bytes) -> None:
    response = client.post(URL, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["errors"][0]["message"].startswith("Invalid JSON")
