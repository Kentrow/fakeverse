# HTTP API

The HTTP API exposes the generator over HTTP. Install it with the `api` extra and run it with
Uvicorn, or with the Docker image (see the [deployment guide](deployment.md)):

```bash
pip install "fakeverse[api]"
uvicorn fakeverse.api.app:app --no-access-log
```

- Every API endpoint is under `/v1` (except `/metrics`, `/docs` and `/openapi.json`); a
  breaking change would come with `/v2`.
- No authentication. CORS is open to every origin by default.
- The interactive documentation is served at `/docs`, the OpenAPI document at `/openapi.json`.
- The concepts (types, seeds, locales, uniqueness, templates) are described in
  [How generation works](generation.md).

The examples below use a local instance at `http://localhost:8000`.

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/health` | `{"status": "ok"}`, not rate limited |
| `GET` | `/v1/meta` | Versions, limits and disclaimer |
| `GET` | `/v1/types` | Core taxonomy: composite types, their fields, atomic types |
| `GET` | `/v1/universes` | List of universes |
| `GET` | `/v1/universes/{universe}` | Details of a universe and the types it supports |
| `GET` | `/v1/universes/{universe}/generate/{type}` | Generation of a type |
| `POST` | `/v1/universes/{universe}/generate` | Generation from a template, in a JSON body |
| `GET` | `/v1/universes/{universe}/generate?template=...` | Generation from a template, as base64url |
| `GET` | `/metrics` | Prometheus metrics, when enabled, not rate limited |

`/v1/universes` and `/v1/universes/{universe}` accept `locale` (names are translated) and
`data_version`. The details of a universe contain its `id`, `name`, `locales`,
`default_locale`, `sources`, `maintainers`, `place_levels`, `capabilities` (supported core
and extension types), `locale_coverage` (share of the localized values translated in each
locale) and `meta` (the data version).

`/v1/meta`:

```json
{
  "package_version": "0.1.0",
  "engine_revision": 1,
  "data_versions": ["0.1.0"],
  "default_data_version": "0.1.0",
  "limits": { "max_count": 1000, "max_template_leaves": 50, "max_template_depth": 4 },
  "disclaimer": "Fakeverse is an independent, non-commercial open source project. ..."
}
```

## Generating a type

```bash
curl "http://localhost:8000/v1/universes/lotr/generate/person?count=3&seed=42&locale=fr"
curl "http://localhost:8000/v1/universes/starwars/generate/starship?count=10&format=csv"
```

| Parameter | Default | Description |
|---|---|---|
| `count` | `1` | From 1 to the `max_count` of the instance (1000 by default) |
| `seed` | random | From 0 to 2^63 - 1 |
| `locale` | default locale of the universe | BCP-47 tag, e.g. `fr` or `fr-FR` |
| `data_version` | most recent | Data version, see `/v1/meta` |
| `unique` | absent | Absent: best effort; `true`: strict; `false`: duplicates allowed |
| `explain` | `false` | Origin of each value; not available with CSV |
| `format` | `json` | `json`, `ndjson` or `csv`; takes precedence over `Accept` |
| `gender` | | `masculine`, `feminine` or `neutral`; `person` and its atomic types only |
| `people` | | Id of a people; `person` and its atomic types only |

A parameter that does not apply to the requested type is an error (`invalid-parameter`).

## Generating from a template

```bash
curl -X POST "http://localhost:8000/v1/universes/lotr/generate" \
  -H "Content-Type: application/json" \
  -d '{"template": {"name": "person.full_name", "town": "person.address.locality"}, "count": 10}'
```

The body is a JSON object of at most 64 KB. Only `template` is required:

```json
{
  "template": { "name": "person.full_name", "employer": "organization.name" },
  "count": 10,
  "seed": 42,
  "locale": "fr",
  "data_version": "0.1.0",
  "unique": null,
  "explain": false,
  "format": "json",
  "colocate": [["person", "organization"]]
}
```

`POST` responses are never cached. For a cacheable request, send the same template with
`GET`, encoded as base64url JSON (padding optional, 64 KB at most once decoded), with the
other members as query parameters. `colocate` then takes the form
`person,organization;person%232,address` (groups separated by `;`, `#` encoded as `%23`):

```bash
TEMPLATE=$(printf '%s' '{"name":"person.full_name","town":"person.address.locality"}' \
  | base64 | tr '+/' '-_' | tr -d '=\n')
curl "http://localhost:8000/v1/universes/lotr/generate?template=$TEMPLATE&count=10&seed=42"
```

## Responses

### JSON

```json
{
  "data": ["Andwise", "Orodreth"],
  "meta": {
    "universe": "lotr",
    "type": "first_name",
    "count": 2,
    "seed": 42,
    "seed_generated": false,
    "locale": "en",
    "locale_fallbacks": 0,
    "data_version": "0.1.0",
    "engine_revision": 1,
    "duplicates": 0
  }
}
```

For a template, `meta.type` is `"template"`.

### NDJSON and CSV

- **NDJSON** (`application/x-ndjson`): one item per line; the metadata is in the headers only.
- **CSV** (`text/csv; charset=utf-8`): a header line, then one item per line. Objects are
  flattened into dotted columns (`address.locality`), atomic types produce a `value` column
  and null values become empty cells.

The format is chosen with `format`, or else with the `Accept` header.

### Headers

Every generation carries `Fakeverse-Seed`, `Fakeverse-Data-Version`,
`Fakeverse-Engine-Revision`, `Fakeverse-Locale`, `Fakeverse-Locale-Fallbacks` and
`Fakeverse-Duplicates`, exposed to browsers through CORS.

## Errors

Errors follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
(`application/problem+json`); every problem type is described in [API problems](problems.md).
The `type` of a problem, `/problems/<slug>`, is relative to the API and redirects to its
documentation.

| Status | Problem | Case |
|---|---|---|
| 404 | `universe-not-found` | Unknown or withdrawn universe |
| 404 | `type-not-supported` | Unknown type, or type not supported by the universe |
| 404 | `data-version-not-found` | Unknown data version |
| 410 | `data-version-retired` | Data version of an older engine revision |
| 413 | `payload-too-large` | Template over 64 KB |
| 422 | `invalid-parameter` | Invalid or inapplicable parameter |
| 422 | `count-too-large` | `count` over the maximum |
| 422 | `locale-not-supported` | Language not supported by the universe |
| 422 | `invalid-template` | Invalid template, with every faulty path |
| 422 | `pool-exhausted` | `unique=true` cannot be satisfied |
| 429 | `rate-limited` | Rate limit reached |

## Rate limiting

Requests are limited per client IP address with a token bucket: by default 60 requests per
minute, with bursts of 20. IPv6 clients are limited per /64 network. Responses carry
`RateLimit-Limit` (the size of the bucket), `RateLimit-Remaining` and `RateLimit-Reset`, and
`429` responses `Retry-After`. `/v1/health`, `/metrics` and `OPTIONS` preflight requests are not counted.

## Caching

A request with an explicit seed is deterministic, hence cacheable:

| Request | `Cache-Control` |
|---|---|
| `seed` and `data_version` given | `public, max-age=31536000, immutable` |
| `seed` given, `data_version` omitted | `public, max-age=3600` |
| no `seed` | `no-store` |

Responses with a seed carry an `ETag`, and the API answers `If-None-Match` with
`304 Not Modified`. Responses vary on `Accept`.
