# API problems

Errors of the Fakeverse API follow [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
(`Content-Type: application/problem+json`). Every problem has these members:

| Member | Content |
|---|---|
| `type` | `/problems/<slug>`, one of the slugs below; on the API, it leads to this documentation |
| `title` | Short summary of the problem type |
| `status` | HTTP status code |
| `detail` | Explanation of this occurrence |
| `instance` | Path of the request |

Some problems add members, listed with each slug.

```json
{
  "type": "/problems/type-not-supported",
  "title": "Type not supported",
  "status": 404,
  "detail": "Universe 'lotr' does not support type 'starship'. Supported: person, address, ...",
  "instance": "/v1/universes/lotr/generate/starship",
  "supported_types": ["person", "address", "..."]
}
```

## `universe-not-found` (404)

The universe does not exist in the requested data version, or it has been disabled.

## `type-not-supported` (404)

The type is unknown, or the universe has no data to generate it. Extra member:
`supported_types`, the types the universe supports.

## `data-version-not-found` (404)

The requested `data_version` is not served. The `detail` lists the available versions, also
given by `GET /v1/meta`.

## `data-version-retired` (410)

The requested `data_version` was produced by an older engine revision: the same seed no longer
gives the same result with the current engine. Install the package pinned to that version to
reproduce it (`pip install fakeverse==<version>`).

## `invalid-parameter` (422)

A parameter is malformed, out of range, unknown, or not applicable to the request (for
instance `gender` with a type other than `person` and its atomic types, or `explain` with
`format=csv`). For a malformed, out-of-range or unknown parameter, the extra member `errors`
lists `{name, location, message}`; a parameter that does not apply is explained in `detail`.

## `count-too-large` (422)

`count` exceeds the maximum of the server. Extra member: `max_count`. For a template, the
number of generated instances (`count` times the number of distinct instances of the template)
is also limited to 5 times `max_count`; the extra member `max_instances` then gives that limit.

## `locale-not-supported` (422)

The language of the requested locale is not one of the languages of the universe. Extra member:
`supported_locales`.

## `invalid-template` (422)

The template is malformed. Every faulty leaf is reported at once. Extra member: `errors`, a
list of `{path, leaf, reason}` where `path` is a JSON pointer to the leaf in the template, or
`/colocate/<group>/<member>` for a colocation group.

## `pool-exhausted` (422)

Strict uniqueness (`unique=true`) cannot be satisfied: the universe does not have enough
distinct values for the requested
count. Extra member: `unique_count`, the number of unique items that could be
generated.

## `payload-too-large` (413)

The body of a template request, or the template decoded from the `template` parameter of the
GET variant, exceeds 64 KB.

## `rate-limited` (429)

Too many requests from this client. The `Retry-After` header and the extra member
`retry_after` give the number of seconds to wait.

## `not-found` (404)

No endpoint matches the path.

## `method-not-allowed` (405)

The endpoint does not accept this HTTP method.
