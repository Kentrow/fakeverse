# Deploying the API

The API ships as a Docker image (`ghcr.io/kentrow/fakeverse`), published at each release. It
runs Uvicorn with a single worker, as an unprivileged user, and reports its health on
`/v1/health`.

```bash
docker run -d --name fakeverse -p 127.0.0.1:8000:8000 \
  -e FAKEVERSE_TRUSTED_PROXIES=172.16.0.0/12 \
  ghcr.io/kentrow/fakeverse:0.1
```

## Data versions

The image contains one data snapshot per release made with the current engine revision, built
from the git tags by `scripts/build_snapshots.py`, plus the data of the release itself. They
live in `/opt/data/<version>/` (`FAKEVERSE_DATA_DIR`). Requests choose a version with
`data_version`, and default to the most recent one. Versions of an older engine revision
answer `410 data-version-retired`.

To build the image yourself, build from a clone with its tags (`git fetch --tags`):

```bash
docker build -t fakeverse .
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `FAKEVERSE_DATA_DIR` | `/opt/data` in the image | Snapshots `<version>/<universe>.yaml` |
| `FAKEVERSE_MAX_COUNT` | `1000` | Maximum `count` per request |
| `FAKEVERSE_MAX_TEMPLATE_LEAVES` | `50` | Maximum leaves per template |
| `FAKEVERSE_RATE_LIMIT` | `60/minute` | Refill rate per client IP; `0` disables rate limiting |
| `FAKEVERSE_RATE_BURST` | `20` | Size of the token bucket |
| `FAKEVERSE_TRUSTED_PROXIES` | empty | CIDRs allowed to set `X-Forwarded-For` |
| `FAKEVERSE_DISABLED_UNIVERSES` | empty | Universes to withdraw, comma separated |
| `FAKEVERSE_CORS_ORIGINS` | `*` | Allowed origins, comma separated |
| `FAKEVERSE_METRICS_ENABLED` | `false` | Expose Prometheus metrics on `/metrics` |
| `FAKEVERSE_LOG_LEVEL` | `info` | Level of the JSON access log |

Settings are read at start-up: restart the container after a change. Withdrawing a universe
(see [TAKEDOWN.md](../TAKEDOWN.md)) only takes a restart with `FAKEVERSE_DISABLED_UNIVERSES`,
no rebuild.

## Behind a reverse proxy

**Client IP.** The rate limit and the logs use the client IP. Behind a proxy, every request
comes from the proxy, so:

1. make the proxy set `X-Forwarded-For` (append the client address, do not trust the one sent
   by the client);
2. list the address of the proxy in `FAKEVERSE_TRUSTED_PROXIES` (for Docker networks, the
   subnet of the network, e.g. `172.16.0.0/12`).

The API then takes the rightmost address of `X-Forwarded-For` that is not a trusted proxy.
`X-Forwarded-For` from any other source is ignored, so clients cannot spoof their address.
The image runs Uvicorn with `--no-proxy-headers`, so that this logic is the only one.

**Rate limiting.** The state of the rate limit is local to the process: run a single
container (and a single worker, the default). IPv4 clients are limited by address, IPv6
clients by /64 network; `OPTIONS` preflight requests are not counted. Pass the `RateLimit-Limit`,
`RateLimit-Remaining`, `RateLimit-Reset` and `Retry-After` headers through.

**Caching.** Requests with an explicit seed are deterministic, and the API says so:

| Request | `Cache-Control` |
|---|---|
| `seed` and `data_version` given | `public, max-age=31536000, immutable` |
| `seed` given, `data_version` omitted | `public, max-age=3600` |
| no `seed` | `no-store` |

A caching proxy or a CDN can follow these headers as they are. Responses with a seed also
carry an `ETag`, and the API answers `If-None-Match` with `304 Not Modified`. Template requests
sent with `POST` are never cached; the `GET` variant (template as base64url in the query) follows
the same rules as other generations. Note that GET templates appear in the access logs of
proxies, which record query strings; the API itself never logs them. Keep the query string in
the cache key, and add the `Accept` header to it if clients negotiate the format with `Accept`
rather than `format`.

**Metrics.** `/metrics` is not rate limited and should not be public: restrict it to your
monitoring network at the proxy.

**Body size.** Template bodies are limited to 64 KB by the API; the proxy can enforce the same
limit.

### Caddy

```caddyfile
api.example.org {
    @metrics path /metrics
    respond @metrics 404
    reverse_proxy fakeverse:8000
}
```

Caddy sets `X-Forwarded-For` itself and replaces any value sent by the client.

### nginx

```nginx
server {
    listen 443 ssl;
    server_name api.example.org;
    client_max_body_size 64k;

    location = /metrics { deny all; }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

With nginx on the same host and the port published on `127.0.0.1`, the connection comes from
the Docker gateway: set `FAKEVERSE_TRUSTED_PROXIES` to the subnet of the Docker bridge
(`172.17.0.0/16` by default).

## Capacity

Indicative figures for a single worker on a 4-core Xeon at 2.7 GHz (the load client running on
the same machine), with 16 concurrent clients requesting `person`:

| `count` | Requests per second | Items per second | p95 latency |
|---|---|---|---|
| 1 | about 360 | about 360 | 60 ms |
| 10 | about 180 | about 1,800 | 110 ms |
| 100 | about 30 | about 3,200 | 680 ms |

With the default rate limit (60 requests per minute per client), one worker serves
hundreds of active clients. Generation is CPU bound: if needed, run more containers behind
the proxy, keeping in mind that each one has its own rate limit state.

## Logs and monitoring

The API writes one JSON line per request on stdout: `method`, `path`, `status`,
`duration_ms`, `universe`, `type`, `count`, `format` and `client_ip` with its last byte
(IPv4) or group (IPv6) masked. The content of templates is never logged.

With `FAKEVERSE_METRICS_ENABLED=true`, `/metrics` exposes
`fakeverse_http_requests_total{route,status}`,
`fakeverse_http_request_duration_seconds{route}`,
`fakeverse_generated_items_total{universe,type}`, `fakeverse_rate_limited_total` and
`fakeverse_info{package_version,engine_revision,data_version}`.

The Docker `HEALTHCHECK` calls `/v1/health` every 30 seconds.

## Checking a deployment setup

`scripts/check_deployment.sh` builds the image and runs it behind nginx (configured as above)
in a Docker network, then checks from two clients with their own IP addresses that the rate
limit applies per client even with a forged `X-Forwarded-For`, that `/metrics` is not public
and that cache headers reach the clients. It needs Docker and takes about a minute.
