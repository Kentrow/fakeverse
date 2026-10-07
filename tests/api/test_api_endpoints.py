import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from fakeverse import ENGINE_REVISION, __version__
from fakeverse.api.app import create_app
from fakeverse.api.problems import STATUS
from fakeverse.api.settings import Settings
from fakeverse.types import ATOMIC_ALIASES, COMPOSITES

PROBLEM = "application/problem+json"


def test_health(client: TestClient) -> None:
    response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_meta(client: TestClient) -> None:
    meta = client.get("/v1/meta").json()
    assert meta["package_version"] == __version__
    assert meta["engine_revision"] == ENGINE_REVISION
    assert meta["data_versions"] == ["0.0.9", "0.1.0"]
    assert meta["default_data_version"] == "0.1.0"
    assert meta["limits"] == {"max_count": 1000, "max_template_leaves": 50, "max_template_depth": 4}
    assert "not affiliated" in meta["disclaimer"]


def test_types(client: TestClient) -> None:
    types = client.get("/v1/types").json()
    assert list(types["composites"]) == list(COMPOSITES)
    assert types["composites"]["address"][1] == {
        "name": "postal_code",
        "type": "string",
        "nullable": True,
    }
    assert types["atomic"]["organization_name"] == "organization.name"
    assert len(types["atomic"]) == len(ATOMIC_ALIASES)


def test_universes(client: TestClient) -> None:
    body = client.get("/v1/universes").json()
    assert body["meta"] == {"data_version": "0.1.0"}
    assert [u["id"] for u in body["data"]] == ["minimal", "test-world"]
    french = client.get("/v1/universes", params={"locale": "fr_FR"}).json()["data"]
    assert french[1] == {
        "id": "test-world",
        "name": "Monde de test",
        "locales": ["en", "fr"],
        "default_locale": "en",
    }
    german = client.get("/v1/universes", params={"locale": "de"}).json()["data"]
    assert german[1]["name"] == "Test World"
    old = client.get("/v1/universes", params={"data_version": "0.0.9"}).json()
    assert [u["id"] for u in old["data"]] == ["minimal"]
    assert old["meta"] == {"data_version": "0.0.9"}


def test_universe_detail(client: TestClient) -> None:
    detail = client.get("/v1/universes/test-world", params={"locale": "fr"}).json()
    assert detail["name"] == "Monde de test"
    assert detail["place_levels"] == {
        "area": "Région",
        "subdivision": "District",
        "locality": "Ville",
    }
    assert detail["sources"]["translations"] == {"fr": "Fakeverse maintainers"}
    assert detail["maintainers"] == ["Kentrow"]
    assert "person" in detail["capabilities"]["core"]
    assert detail["capabilities"]["extensions"][0] == {
        "id": "relic",
        "label": "Relique",
        "fields": ["name", "kind", "age"],
    }
    assert detail["locale_coverage"] == {"en": 1.0, "fr": 0.9518}
    minimal = client.get("/v1/universes/minimal", params={"locale": "de"}).json()
    assert minimal["place_levels"] == {
        "area": "Area",
        "subdivision": "Subdivision",
        "locality": "Locality",
    }


def test_unknown_universe(client: TestClient) -> None:
    response = client.get("/v1/universes/lotr")
    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM
    assert response.json() == {
        "type": "/problems/universe-not-found",
        "title": "Universe not found",
        "status": 404,
        "detail": "Unknown universe 'lotr'. Available: minimal, test-world.",
        "instance": "/v1/universes/lotr",
    }


def test_disabled_universes(make_client: object) -> None:
    client = make_client(disabled_universes="test-world, other")  # type: ignore[operator]
    assert [u["id"] for u in client.get("/v1/universes").json()["data"]] == ["minimal"]
    for path in ("/v1/universes/test-world", "/v1/universes/test-world/generate/person"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown universe 'test-world'. Available: minimal."
    response = client.post(
        "/v1/universes/test-world/generate", json={"template": {"a": "first_name"}}
    )
    assert response.status_code == 404


def test_unknown_route_and_method(client: TestClient) -> None:
    missing = client.get("/v1/nope")
    assert (missing.status_code, missing.json()["type"]) == (404, "/problems/not-found")
    wrong = client.delete("/v1/health")
    assert (wrong.status_code, wrong.json()["type"]) == (405, "/problems/method-not-allowed")


def test_unknown_parameters_are_rejected(client: TestClient) -> None:
    for path in ("/v1/meta", "/v1/types", "/v1/universes", "/v1/universes/minimal"):
        response = client.get(path, params={"colour": "red"})
        assert response.status_code == 422, path
        assert response.json()["errors"] == [
            {"name": "colour", "location": "query", "message": "Unknown parameter"}
        ]


def test_openapi(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/v1/universes/{universe}/generate/{type_id}" in schema["paths"]
    assert "/v1/universes/{universe}/generate" in schema["paths"]
    assert client.get("/docs").status_code == 200


def test_cors(client: TestClient) -> None:
    response = client.get("/v1/health", headers={"Origin": "https://example.org"})
    assert response.headers["access-control-allow-origin"] == "*"
    assert "Fakeverse-Seed" in response.headers["access-control-expose-headers"]


def test_default_store_serves_the_package_data() -> None:
    client = TestClient(create_app(Settings(rate_limit="0")))
    assert client.get("/v1/meta").json()["data_versions"] == [__version__]
    assert [u["id"] for u in client.get("/v1/universes").json()["data"]] == ["lotr", "starwars"]


def test_every_problem_is_documented() -> None:
    doc = (Path(__file__).parents[2] / "docs" / "problems.md").read_text()
    for slug, status in STATUS.items():
        assert f"## `{slug}` ({status})" in doc, slug


def test_problem_types_lead_to_their_documentation(client: TestClient) -> None:
    problem = client.get("/v1/universes/narnia").json()
    response = client.get(problem["type"], follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://github.com/Kentrow/fakeverse/blob/main/docs/problems.md#universe-not-found-404"
    )
    unknown = client.get("/problems/teapot")
    assert unknown.status_code == 404
    assert unknown.json()["type"] == "/problems/not-found"


def test_openapi_documents_bodies_and_problems(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    assert {"Problem", "Generation", "GenerationMeta", "Meta", "UniverseDetail"} <= set(components)
    assert "HTTPValidationError" not in components
    generate = schema["paths"]["/v1/universes/{universe}/generate/{type_id}"]["get"]["responses"]
    assert set(generate["200"]["content"]) == {
        "application/json",
        "application/x-ndjson",
        "text/csv",
    }
    assert "304" in generate
    for status in ("404", "410", "422", "429"):
        assert list(generate[status]["content"]) == ["application/problem+json"]
    post = schema["paths"]["/v1/universes/{universe}/generate"]["post"]["responses"]
    assert "304" not in post
    assert "413" in post


def test_openapi_references_resolve(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    refs = re.findall(r'"\$ref": "([^"]+)"', json.dumps(schema))
    components = schema["components"]["schemas"]
    for ref in refs:
        assert ref.startswith("#/components/schemas/"), ref
        assert ref.removeprefix("#/components/schemas/") in components, ref
