"""GET variant of template generation, with the template as base64url JSON."""

import base64
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fakeverse.api.problems import Problem
from fakeverse.api.routes import MAX_ENCODED_TEMPLATE, decode_template

URL = "/v1/universes/test-world/generate"
TEMPLATE = {"name": "person.full_name", "town": "person.address.locality", "r": "relic.name"}


def encode(template: Any, *, padding: bool = False) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(template).encode()).decode()
    return raw if padding else raw.rstrip("=")


def test_same_rows_as_post(client: TestClient) -> None:
    body = {"template": TEMPLATE, "count": 4, "seed": 9, "locale": "fr"}
    post = client.post(URL, json=body).json()
    get = client.get(
        URL, params={"template": encode(TEMPLATE), "count": 4, "seed": 9, "locale": "fr"}
    )
    assert get.status_code == 200
    assert get.json() == post
    assert get.headers["Fakeverse-Seed"] == "9"


def test_padding_is_optional(client: TestClient) -> None:
    for padding in (False, True):
        params = {"template": encode({"a": "first_name"}, padding=padding), "seed": 1}
        assert client.get(URL, params=params).status_code == 200


def test_cache_headers_and_etag(client: TestClient) -> None:
    params = {"template": encode(TEMPLATE), "seed": 3}
    first = client.get(URL, params=params)
    assert first.headers["Cache-Control"] == "public, max-age=3600"
    assert "Accept" in first.headers["Vary"]
    tag = first.headers["ETag"]
    again = client.get(URL, params=params, headers={"If-None-Match": tag})
    assert again.status_code == 304
    pinned = client.get(URL, params={**params, "data_version": "0.1.0"})
    assert pinned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    random = client.get(URL, params={"template": encode(TEMPLATE)})
    assert random.headers["Cache-Control"] == "no-store"
    assert "ETag" not in random.headers


def test_etag_ignores_the_json_spelling(client: TestClient) -> None:
    compact = base64.urlsafe_b64encode(b'{"a":"first_name"}').decode().rstrip("=")
    spaced = base64.urlsafe_b64encode(b'{ "a" : "first_name" }').decode().rstrip("=")
    tags = [
        client.get(URL, params={"template": t, "seed": 1}).headers["ETag"]
        for t in (compact, spaced)
    ]
    assert tags[0] == tags[1]


def test_formats(client: TestClient) -> None:
    params = {"template": encode(TEMPLATE), "seed": 1, "count": 2, "format": "csv"}
    assert client.get(URL, params=params).text.splitlines()[0] == "name,town,r"


@pytest.mark.parametrize(
    ("template", "message"),
    [
        ("@@@", "Invalid base64url"),
        ("a", "Invalid base64url"),
        (base64.urlsafe_b64encode(b"\xff\xfe").decode(), "Invalid UTF-8"),
        (base64.urlsafe_b64encode(b"{nope").decode(), "Invalid JSON"),
        (encode(["person.email"]), "valid dictionary"),
    ],
)
def test_invalid_templates(client: TestClient, template: str, message: str) -> None:
    response = client.get(URL, params={"template": template})
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "/problems/invalid-parameter"
    assert message in body["errors"][0]["message"]


def test_errors(client: TestClient) -> None:
    missing = client.get(URL)
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["name"] == "template"
    bad_path = client.get(
        URL,
        params={"template": encode({"a": "person.nope"}), "seed": 1},
        headers={"If-None-Match": "*"},
    )
    assert bad_path.status_code == 422
    assert bad_path.json()["type"] == "/problems/invalid-template"
    unknown = client.get(URL, params={"template": encode(TEMPLATE), "gender": "feminine"})
    assert unknown.status_code == 422


def test_size_limit() -> None:
    # HTTP clients refuse such URLs anyway; the server still bounds what it decodes.
    with pytest.raises(Problem) as info:
        decode_template("A" * (MAX_ENCODED_TEMPLATE + 1))
    assert info.value.slug == "payload-too-large"
    assert decode_template(encode({"a": "first_name"})) == {"a": "first_name"}


def test_openapi(client: TestClient) -> None:
    get = client.get("/openapi.json").json()["paths"]["/v1/universes/{universe}/generate"]["get"]
    assert {"200", "304", "413", "422"} <= set(get["responses"])
    assert [p["name"] for p in get["parameters"]][1] == "template"


def test_etag_follows_the_key_order(client: TestClient) -> None:
    ab = client.get(URL, params={"template": encode({"a": "first_name", "b": "area"}), "seed": 1})
    ba = client.get(URL, params={"template": encode({"b": "area", "a": "first_name"}), "seed": 1})
    assert ab.headers["ETag"] != ba.headers["ETag"]


def test_non_standard_json(client: TestClient) -> None:
    for raw in (b'{"a": NaN}', b'{"a": ' + b"1" * 5000 + b"}"):
        template = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        response = client.get(URL, params={"template": template, "seed": 1})
        assert response.status_code == 422
        assert response.json()["errors"][0]["message"].startswith("Invalid JSON")


def test_exact_size_limit() -> None:
    at_limit = base64.urlsafe_b64encode(b" " * 65536).decode()
    with pytest.raises(Problem):  # 64 KiB of spaces is not a template, but it is not too large
        decode_template(at_limit)
    over = base64.urlsafe_b64encode(b" " * 65537).decode()
    with pytest.raises(Problem) as info:
        decode_template(over)
    assert info.value.slug == "payload-too-large"
