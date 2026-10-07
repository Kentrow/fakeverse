"""Rate limiting, trusted proxies, settings, logs and metrics."""

import json
from pathlib import Path

import pytest
from api_support import ClientFactory, FakeClock
from pydantic import ValidationError

from fakeverse.api.ratelimit import RateLimiter, client_ip, rate_key, truncate_ip
from fakeverse.api.settings import Settings
from fakeverse.api.snapshots import SnapshotStore
from fakeverse.releases import is_semver, read_releases, semver_key

UNIVERSES = "/v1/universes"


def test_rate_limit_burst_and_refill(make_client: ClientFactory) -> None:
    clock = FakeClock()
    client = make_client(clock=clock, rate_limit="60/minute", rate_burst=3)
    responses = [client.get(UNIVERSES) for _ in range(4)]
    assert [r.status_code for r in responses] == [200, 200, 200, 429]
    assert responses[0].headers["RateLimit-Limit"] == "3"
    assert responses[0].headers["RateLimit-Remaining"] == "2"
    assert responses[2].headers["RateLimit-Remaining"] == "0"
    assert responses[2].headers["RateLimit-Reset"] == "3"
    limited = responses[3]
    assert limited.headers["Retry-After"] == "1"
    assert limited.json()["type"] == "/problems/rate-limited"
    assert limited.json()["retry_after"] == 1
    clock.now += 1
    assert client.get(UNIVERSES).status_code == 200
    assert client.get(UNIVERSES).status_code == 429


def test_health_and_metrics_are_exempt(make_client: ClientFactory) -> None:
    client = make_client(clock=FakeClock(), rate_limit="1/hour", rate_burst=1, metrics_enabled=True)
    assert client.get(UNIVERSES).status_code == 200
    assert client.get(UNIVERSES).status_code == 429
    for _ in range(3):
        health = client.get("/v1/health")
        assert health.status_code == 200
        assert "RateLimit-Limit" not in health.headers
        assert client.get("/metrics").status_code == 200


def test_rate_limit_disabled(client: object) -> None:
    response = client.get(UNIVERSES)  # type: ignore[attr-defined]
    assert "RateLimit-Limit" not in response.headers


def test_forwarded_for_is_ignored_from_untrusted_peers(make_client: ClientFactory) -> None:
    client = make_client(
        clock=FakeClock(), rate_limit="1/hour", rate_burst=1, trusted_proxies="0.0.0.0/0"
    )
    # TestClient connects from "testclient", which is not an IP, hence never trusted: both
    # requests share one bucket whatever X-Forwarded-For says.
    assert client.get(UNIVERSES, headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert client.get(UNIVERSES, headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429


def test_client_ip() -> None:
    proxies = Settings(trusted_proxies="10.0.0.0/8, ::1/128").proxy_networks
    assert client_ip("10.0.0.2", "203.0.113.7", proxies) == "203.0.113.7"
    assert client_ip("10.0.0.2", "198.51.100.1, 203.0.113.7, 10.0.0.9", proxies) == "203.0.113.7"
    assert client_ip("192.0.2.1", "203.0.113.7", proxies) == "192.0.2.1"
    assert client_ip("10.0.0.2", None, proxies) == "10.0.0.2"
    assert client_ip("10.0.0.2", "10.0.0.3", proxies) == "10.0.0.2"
    assert client_ip("::1", "garbage, 203.0.113.8", proxies) == "203.0.113.8"
    assert client_ip(None, "203.0.113.7", proxies) == "unknown"


def test_truncate_ip() -> None:
    assert truncate_ip("203.0.113.77") == "203.0.113.0"
    assert truncate_ip("2001:db8::1234:5678") == "2001:db8::1234:0"
    assert truncate_ip("testclient") == "unknown"


def test_limiter_evicts_the_least_recently_used(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(rate=1.0, burst=2, clock=FakeClock())
    monkeypatch.setattr("fakeverse.api.ratelimit.MAX_TRACKED", 3)
    for key in ("a", "b", "c"):
        limiter.check(key)
    limiter.check("a")
    limiter.check("d")
    assert list(limiter._buckets) == ["c", "a", "d"]


def test_rate_key() -> None:
    assert rate_key("203.0.113.7") == "203.0.113.7"
    assert (
        rate_key("2001:db8:1:2:3:4:5:6") == rate_key("2001:db8:1:2:ffff::1") == "2001:db8:1:2::/64"
    )
    assert rate_key("testclient") == "testclient"
    assert rate_key("::ffff:1.2.3.4") == "1.2.3.4"
    assert rate_key("::ffff:1.2.3.4") != rate_key("::ffff:5.6.7.8")


def test_ipv6_clients_share_their_64(make_client: ClientFactory) -> None:
    client = make_client(
        clock=FakeClock(), rate_limit="1/hour", rate_burst=1, trusted_proxies="0.0.0.0/0, ::/0"
    )
    app = client.app
    # The test client peer is not an IP: call the limiter through the keys directly.
    limiter = app.state.fakeverse.limiter  # type: ignore[attr-defined]
    assert limiter.check(rate_key("2001:db8::1")).allowed
    assert not limiter.check(rate_key("2001:db8::2")).allowed


def test_options_and_429_carry_cors(make_client: ClientFactory) -> None:
    client = make_client(clock=FakeClock(), rate_limit="1/hour", rate_burst=1)
    origin = {"Origin": "https://example.org"}
    preflight = {**origin, "Access-Control-Request-Method": "POST"}
    for _ in range(3):
        assert client.options(UNIVERSES, headers=preflight).status_code == 200
    assert client.get(UNIVERSES, headers=origin).status_code == 200
    limited = client.get(UNIVERSES, headers=origin)
    assert limited.status_code == 429
    assert limited.headers["access-control-allow-origin"] == "*"


def test_forwarded_for_on_several_lines() -> None:
    proxies = Settings(trusted_proxies="10.0.0.0/8").proxy_networks
    # A client line "6.6.6.6" followed by the proxy line: the proxy line wins.
    assert client_ip("10.0.0.2", ", ".join(["6.6.6.6", "203.0.113.7"]), proxies) == "203.0.113.7"


@pytest.mark.parametrize(
    ("rate", "per_second"),
    [("60/minute", 1.0), ("10/second", 10.0), ("3600/hour", 1.0), ("30", 0.5), ("0", 0.0)],
)
def test_rate_setting(rate: str, per_second: float) -> None:
    assert Settings(rate_limit=rate).rate_per_second == per_second


def test_invalid_settings() -> None:
    with pytest.raises(ValidationError):
        Settings(rate_limit="fast")
    with pytest.raises(ValidationError):
        Settings(trusted_proxies="not-a-cidr")


def test_settings_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FAKEVERSE_MAX_COUNT", "12")
    monkeypatch.setenv("FAKEVERSE_DISABLED_UNIVERSES", "lotr,starwars")
    monkeypatch.setenv("FAKEVERSE_CORS_ORIGINS", "https://a.example, https://b.example")
    monkeypatch.setenv("FAKEVERSE_METRICS_ENABLED", "true")
    monkeypatch.setenv("FAKEVERSE_DATA_DIR", str(tmp_path))
    settings = Settings()
    assert settings.max_count == 12
    assert settings.disabled == ["lotr", "starwars"]
    assert settings.cors_origin_list == ["https://a.example", "https://b.example"]
    assert settings.metrics_enabled
    assert settings.data_dir == tmp_path


def test_access_log(make_client: ClientFactory, capsys: pytest.CaptureFixture[str]) -> None:
    client = make_client()
    capsys.readouterr()
    client.get("/v1/universes/test-world/generate/person", params={"count": 2, "seed": 1})
    client.post(
        "/v1/universes/test-world/generate",
        json={"template": {"secret_key": "person.email"}, "seed": 1},
    )
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    get, post = lines[-2], lines[-1]
    assert get == {
        "method": "GET",
        "path": "/v1/universes/test-world/generate/person",
        "status": 200,
        "duration_ms": get["duration_ms"],
        "universe": "test-world",
        "type": "person",
        "count": 2,
        "format": "json",
        "client_ip": "unknown",
    }
    assert post["type"] == "template"
    assert "secret_key" not in json.dumps(post)


def test_metrics(make_client: ClientFactory) -> None:
    client = make_client(metrics_enabled=True)
    client.get("/v1/universes/test-world/generate/person", params={"count": 3, "seed": 1})
    text = client.get("/metrics").text
    assert 'fakeverse_generated_items_total{type="person",universe="test-world"} 3.0' in text
    assert (
        'fakeverse_http_requests_total{route="/v1/universes/{universe}/generate/{type_id}",'
        'status="200"} 1.0'
    ) in text
    assert "fakeverse_http_request_duration_seconds_bucket" in text
    assert "fakeverse_rate_limited_total 0.0" in text
    assert 'fakeverse_info{data_version="0.1.0",engine_revision="1",package_version=' in text


def test_metrics_disabled(client: object) -> None:
    assert client.get("/metrics").status_code == 404  # type: ignore[attr-defined]


def test_snapshot_store_without_releases(tmp_path: Path, data_dir: Path) -> None:
    (tmp_path / "1.0.0").mkdir()
    (tmp_path / "1.0.0-rc.1").mkdir()
    store = SnapshotStore.load(tmp_path, [])
    assert store.versions == ["1.0.0-rc.1", "1.0.0"]
    assert store.default_version == "1.0.0"
    assert store.retired == {}


def test_releases(tmp_path: Path) -> None:
    assert read_releases(tmp_path / "missing.toml") == []
    path = tmp_path / "releases.toml"
    path.write_text('[[releases]]\nversion = "1.0.0"\nengine_revision = 1\ndate = "2026-01-02"\n')
    (release,) = read_releases(path)
    assert (release.version, release.engine_revision, release.date.isoformat()) == (
        "1.0.0",
        1,
        "2026-01-02",
    )
    path.write_text('[[releases]]\nversion = "v1"\nengine_revision = 1\ndate = 2026-01-02\n')
    with pytest.raises(ValueError, match="invalid version"):
        read_releases(path)


def test_semver() -> None:
    assert is_semver("1.2.3-rc.1+build.5")
    assert not is_semver("1.2")
    assert sorted(["1.10.0", "1.2.0", "1.2.0-rc.1"], key=semver_key) == [
        "1.2.0-rc.1",
        "1.2.0",
        "1.10.0",
    ]
    ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2"]
    ordered += ["1.0.0-beta.11", "1.0.0-rc.1", "1.0.0-rc.2", "1.0.0-rc.10", "1.0.0"]
    assert sorted(reversed(ordered), key=semver_key) == ordered
    with pytest.raises(ValueError, match="SemVer"):
        semver_key("one")
