from fastapi.testclient import TestClient

from fakeverse.api.cache import cache_control, etag, matches

PERSON = "/v1/universes/test-world/generate/person"


def test_cache_control_rules(client: TestClient) -> None:
    pinned = client.get(PERSON, params={"seed": 1, "data_version": "0.1.0"})
    assert pinned.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    latest = client.get(PERSON, params={"seed": 1})
    assert latest.headers["Cache-Control"] == "public, max-age=3600"
    random = client.get(PERSON)
    assert random.headers["Cache-Control"] == "no-store"
    assert "ETag" not in random.headers


def test_etag_and_304(client: TestClient) -> None:
    first = client.get(PERSON, params={"seed": 5, "count": 2})
    tag = first.headers["ETag"]
    assert tag.startswith('"')
    again = client.get(PERSON, params={"seed": 5, "count": 2}, headers={"If-None-Match": tag})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["ETag"] == tag
    assert again.headers["Cache-Control"] == "public, max-age=3600"
    weak = client.get(
        PERSON, params={"seed": 5, "count": 2}, headers={"If-None-Match": f'"other", W/{tag}'}
    )
    assert weak.status_code == 304
    other = client.get(PERSON, params={"seed": 5, "count": 3}, headers={"If-None-Match": tag})
    assert other.status_code == 200
    assert other.headers["ETag"] != tag


def test_etag_depends_on_resolved_inputs(client: TestClient) -> None:
    def tag(**params: object) -> str:
        return client.get(PERSON, params={"seed": 1, **params}).headers["ETag"]

    assert tag() == tag(data_version="0.1.0")
    assert tag(locale="fr_FR") == tag(locale="fr-FR")
    assert tag() != tag(locale="fr")
    assert tag() != tag(format="csv")
    assert tag() != tag(explain="true")


def test_post_is_not_cacheable(client: TestClient) -> None:
    response = client.post(
        "/v1/universes/test-world/generate", json={"template": {"a": "first_name"}, "seed": 1}
    )
    assert response.headers["Cache-Control"] == "no-store"
    assert "ETag" not in response.headers


def test_helpers() -> None:
    assert cache_control(seed_given=False, data_version_given=True) == "no-store"
    assert etag("a/b", "1.0.0", {"x": 1}) == etag("a/b", "1.0.0", {"x": 1})
    assert etag("a/b", "1.0.0", {"x": 1}) != etag("a/b", "1.0.1", {"x": 1})
    assert matches("*", '"x"')
    assert not matches(None, '"x"')
    assert not matches('"y"', '"x"')


def test_vary_accept(client: TestClient) -> None:
    assert "Accept" in client.get(PERSON, params={"seed": 1}).headers["Vary"]
    post = client.post(
        "/v1/universes/test-world/generate", json={"template": {"a": "first_name"}, "seed": 1}
    )
    assert "Accept" in post.headers["Vary"]


def test_if_none_match_never_hides_an_error(client: TestClient) -> None:
    star = {"If-None-Match": "*"}
    unsupported = client.get(
        "/v1/universes/test-world/generate/starship", params={"seed": 1}, headers=star
    )
    assert unsupported.status_code == 404
    bad_people = client.get(PERSON, params={"seed": 1, "people": "nope"}, headers=star)
    assert bad_people.status_code == 422
    assert client.get(PERSON, params={"seed": 1}, headers=star).status_code == 304
