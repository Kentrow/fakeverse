"""Fuzzing of the API: whatever the request, never a 500, and errors are RFC 9457 problems."""

import base64
import json
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from fakeverse.api.app import create_app
from fakeverse.api.settings import Settings

PROFILE = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow],
)

NAMES = st.sampled_from(
    [
        "count",
        "seed",
        "locale",
        "data_version",
        "unique",
        "explain",
        "format",
        "gender",
        "people",
        "colocate",
    ]
)
VALUES = st.sampled_from(
    ["", "0", "1", "-1", "3", "1001", "9223372036854775808", "true", "maybe", "fr", "FR_fr",
     "xx", "csv", "ndjson", "json", "xml", "feminine", "valefolk", "0.1.0", "9.9.9", "%00", "é",
     "person,organization", "person;address", ",", ";;", "person#9,address#1"]
) | st.text(max_size=6)  # fmt: skip
TYPES = st.sampled_from(["person", "first_name", "relic", "barge", "starship", "x", "%2e%2e", ""])
JSONISH = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=8), children, max_size=3)
    ),
    max_leaves=12,
)
LEAVES = st.sampled_from(
    ["person.full_name", "person.address.locality", "first_name", "relic.name", "barge.crew",
     "person#9.email", "person#0.email", "nope", "person.", ".x", "organization.address"]
)  # fmt: skip


@pytest.fixture(scope="module")
def client(data_dir: Any) -> TestClient:
    return TestClient(create_app(Settings(data_dir=data_dir, rate_limit="0", max_count=50)))


def assert_well_formed(response: Any) -> None:
    assert response.status_code < 500, response.text
    if response.status_code >= 400:
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"].startswith("/problems/")


@PROFILE
@given(type_id=TYPES, params=st.dictionaries(NAMES | st.text(max_size=4), VALUES, max_size=5))
def test_generate_never_fails(client: TestClient, type_id: str, params: dict[str, str]) -> None:
    url = f"/v1/universes/test-world/generate/{quote(type_id, safe='')}"
    response = client.get(url, params=params)
    assert_well_formed(response)


@PROFILE
@given(
    template=st.dictionaries(st.text(max_size=5), LEAVES | JSONISH, max_size=4) | JSONISH,
    extra=st.dictionaries(NAMES, JSONISH, max_size=3),
)
def test_template_never_fails(client: TestClient, template: Any, extra: dict[str, Any]) -> None:
    body = {"template": template, **extra}
    response = client.post("/v1/universes/test-world/generate", content=json.dumps(body))
    assert_well_formed(response)


@PROFILE
@given(path=st.text(max_size=12), params=st.dictionaries(NAMES, VALUES, max_size=2))
def test_listings_never_fail(client: TestClient, path: str, params: dict[str, str]) -> None:
    for url in ("/v1/universes", f"/v1/universes/{quote(path, safe='')}"):
        assert_well_formed(client.get(url, params=params))


@PROFILE
@given(
    template=st.text(max_size=40)
    | JSONISH.map(lambda value: base64.urlsafe_b64encode(json.dumps(value).encode()).decode()),
    params=st.dictionaries(NAMES, VALUES, max_size=3),
)
def test_get_template_never_fails(
    client: TestClient, template: str, params: dict[str, str]
) -> None:
    response = client.get(
        "/v1/universes/test-world/generate", params={**params, "template": template}
    )
    assert_well_formed(response)
