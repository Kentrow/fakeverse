"""Colocation groups in template requests (POST body and GET query)."""

import base64
import json

from fastapi.testclient import TestClient

URL = "/v1/universes/test-world/generate"
TEMPLATE = {
    "who": "person.full_name",
    "town": "person.address.locality",
    "org": "organization.address.locality",
}


def encode(template: object) -> str:
    return base64.urlsafe_b64encode(json.dumps(template).encode()).decode().rstrip("=")


def test_post(client: TestClient) -> None:
    body = {"template": TEMPLATE, "count": 30, "seed": 1, "colocate": [["person", "organization"]]}
    rows = client.post(URL, json=body).json()["data"]
    assert all(row["town"] == row["org"] for row in rows)


def test_get_matches_post_and_is_cached(client: TestClient) -> None:
    body = {"template": TEMPLATE, "count": 5, "seed": 2, "colocate": [["person", "organization"]]}
    post = client.post(URL, json=body).json()
    params = {
        "template": encode(TEMPLATE),
        "count": 5,
        "seed": 2,
        "colocate": "person,organization",
    }
    get = client.get(URL, params=params)
    assert get.json() == post
    reordered = client.get(URL, params={**params, "colocate": "organization, person#1"})
    assert reordered.headers["ETag"] == get.headers["ETag"]
    plain = client.get(
        URL, params={key: value for key, value in params.items() if key != "colocate"}
    )
    assert plain.headers["ETag"] != get.headers["ETag"]


def test_invalid_groups(client: TestClient) -> None:
    body = {"template": TEMPLATE, "colocate": [["person", "starship"]]}
    response = client.post(URL, json=body)
    assert response.status_code == 422
    assert response.json()["type"] == "/problems/invalid-template"
    assert response.json()["errors"][0]["path"] == "/colocate/0/1"
    star = client.get(
        URL,
        params={"template": encode(TEMPLATE), "seed": 1, "colocate": "person"},
        headers={"If-None-Match": "*"},
    )
    assert star.status_code == 422
    assert client.post(URL, json={"template": TEMPLATE, "colocate": "person"}).status_code == 422
