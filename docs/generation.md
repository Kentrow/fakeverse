# How generation works

This page describes the concepts shared by the Python package, the Faker provider, the
command line and the HTTP API: types, reproducibility, locales, uniqueness, explain mode and
templates.

## Types

### Composite types

Three core types are composite; every other core type is a projection of one of them.

**`address`**

| Field | Nullable | Content |
| --- | --- | --- |
| `street_address` | no | Rendered from the `street_address` pattern of the universe |
| `postal_code` | yes | Rendered from the `postal_code` pattern, null without one |
| `locality` | no | A locality (a town), drawn according to its weight |
| `subdivision` | yes | The subdivision containing the locality, if any |
| `area` | no | The area containing the locality |
| `formatted` | no | The full address, rendered from the `address_format` pattern |

**`person`**

| Field | Nullable | Content |
| --- | --- | --- |
| `first_name` | no | A first name of the people of the person |
| `last_name` | yes | A family name, null when the people has none |
| `full_name` | no | Rendered from the `name_format` of the people |
| `gender` | yes | `masculine`, `feminine` or `neutral`; null when the first names of the people have no gender |
| `people` | no | The name of the people |
| `address` | no | An `address` in the homelands of the people |
| `email`, `username`, `phone` | yes | Rendered from the patterns of the universe |

Options: `gender` keeps only first names of that gender (and first names without gender),
`people` restricts the person to a people, by id.

**`organization`**

| Field | Nullable | Content |
| --- | --- | --- |
| `name` | no | A canonical organization, or a name rendered from the `organization_name` pattern |
| `kind` | yes | The kind of a canonical organization, null for a generated one |
| `address` | no | An `address` in the places of a canonical organization, anywhere otherwise |
| `phone` | yes | Rendered from the `phone` pattern |

### Atomic types

An atomic type returns one value, projected from a composite type, so it has the same
distribution and the same coherence:

| Type | Projection |
| --- | --- |
| `first_name`, `full_name`, `email`, `username`, `phone` | the same field of `person` |
| `last_name` | `person.last_name`, drawn only among peoples that have family names, so never null |
| `street_address`, `postal_code`, `locality`, `subdivision`, `area` | the same field of `address` |
| `organization_name` | `organization.name` |

### Extension types

Each universe can add its own types, for instance `weapon` in `lotr` or `starship` in
`starwars`. They return an object with a `name` and the fields declared by the universe.

### Supported types

A universe does not declare which core types it supports: support follows from its data. A
universe without organizations and without an `organization_name` pattern does not support
`organization`, for instance. `fakeverse coverage <universe>`,
`UniverseGenerator.capabilities()` and `GET /v1/universes/{universe}` list the supported types.
Asking for another type raises `TypeNotSupported` (`type-not-supported` in the API).

### Coherence

Generated data always respects these invariants, checked by `fakeverse check-coherence` and
by the property tests:

1. The subdivision and the area of an address contain its locality.
2. The address of a person is in the homelands of their people.
3. The first name of a person belongs to their people and matches their gender.
4. `last_name` is null if and only if the people of the person has no family names.
5. When the email pattern uses `{first_name|slug}`, the email contains the slug of the first name.
6. The address of a canonical organization is in its places.
7. No non-nullable string is empty.
8. The same inputs always give the same output.

## Reproducibility

The output of a generation is entirely determined by:

- the engine revision (`ENGINE_REVISION`);
- the data version, which selects the universe data;
- the universe, the type or the template (with its colocation groups), the locale and the
  options (`gender`, `people`, `unique`);
- the seed.

The same inputs always give the same output, on every platform and every supported Python
version. Generations are also stable by prefix: the first k items of a generation of n
items are the k items of the same generation with `count=k`.

The seed is an integer from 0 to 2^63 - 1. Without a seed, one is drawn at random and returned
in the metadata of the result (`meta.seed`, with `meta.seed_generated` set to true),
so that any generation can be replayed.

### Versions

- **Data version**: the version of the package that published the data. The package always
  uses its own data, so its data version is its version. The API can serve the data of several
  releases, selected with `data_version` (the most recent by default).
- **Engine revision**: an integer incremented whenever a change of the engine alters the
  output for identical inputs and data. Such a change is always listed in the
  [changelog](../CHANGELOG.md). The API only serves the data versions of the current engine
  revision; older ones answer `410 data-version-retired`, and the package pinned to that
  version still reproduces them.

A release that changes neither the engine nor the data changes no output. The
[versioning policy](../CONTRIBUTING.md#versioning) says which kind of release each change
makes.

## Locales

Locales are [BCP-47](https://www.rfc-editor.org/info/bcp47) tags of the form
`language[-Script][-REGION]`. They are normalized: `fr_FR`, `FR-fr` and `fr-fr` all become
`fr-FR`. Without a locale, the default locale of the universe is used.

A localized value is resolved with this fallback chain: the exact locale, then its language,
then the default locale of the universe. Falling back to the default locale is a
**fallback**: the number of values that fell back is reported in `meta.locale_fallbacks`
(and the `Fakeverse-Locale-Fallbacks` header). Falling back from `fr-CA` to `fr` is not a
fallback, since the language is the same.

A locale whose language the universe does not support raises `LocaleNotSupported`
(`locale-not-supported` in the API). The Faker provider is more lenient: it uses the default
locale of the universe instead, unless `strict_locale=True`.

## Uniqueness

The `unique` option takes three values:

| Value | Behavior |
| --- | --- |
| absent (default) | **Best effort**: no duplicate as long as the pool allows it. Once an item is still a duplicate after 50 attempts, uniqueness is no longer enforced for the rest of the response. |
| `true` | **Strict**: the same items, but an item that is still a duplicate after 50 attempts raises `PoolExhausted` (`pool-exhausted` in the API). |
| `false` | Duplicates allowed, one draw per item. |

Uniqueness applies to whole items (a whole person, a whole template row). The number of items
equal to an earlier item of the response is reported in `meta.duplicates` (and the
`Fakeverse-Duplicates` header). Best effort and strict give the same items as long as the
pool is large enough. `unique=false` is a different request: for the same seed, it gives
other items.

## Explain mode

By default, values are returned raw. With `explain=True`, every leaf value is replaced by an
object that tells where it comes from:

```json
{ "value": "Frodon", "origin": "canon", "locale": "fr", "fallback": false }
```

- `origin` is `canon` for a value taken from the works, `generated` for a value made up by
  Fakeverse: an element marked `canon: false` in the universe file, or a pattern with random
  parts (`"{first_name}{digits:3}"`). A pattern that only combines canonical values, such as
  `"{first_name} {family_name}"`, stays `canon`.
- `locale` is the locale the value was resolved in, and `fallback` tells whether it fell back
  to the default locale.

Explain mode is not available with the CSV format.

## Templates

A template describes the shape of an output row that combines several types coherently:

```json
{
  "name": "person.full_name",
  "contact": { "email": "person.email", "town": "person.address.locality" },
  "employer": "organization.name",
  "colleague": "person#2.full_name"
}
```

- A template is a JSON object nested on at most 4 levels, with at most 50 leaves (configurable
  in the API).
- Each leaf is a path `type[#n].field[.sub-field...]`. `#n`, from 1 to 9 (1 by default),
  distinguishes several instances of the same type in a row. An atomic type alone is a path
  too: `first_name` is `person.first_name`.
- All the leaves that reference the same instance share it: `person.full_name` and
  `person.email` describe the same person, while `person#2` is another one.
- Each instance has its own seed, so adding or removing a leaf does not change the values of
  the other instances.
- The output follows the structure and the key order of the template.
- The `gender` and `people` options do not apply to templates; `unique` applies to whole rows.
- Paths are checked before any generation, and every faulty path is reported at once
  (`InvalidTemplate`, `invalid-template` in the API).

### Colocation

By default, the instances of a row are independent: a person and an organization can be at
opposite ends of the world. A colocation group makes several instances of `person`, `address`
or `organization` share the same locality, hence the same subdivision and area:

| Interface | Form |
| --- | --- |
| Python | `generator.template(template, colocate=[["person", "organization"]])` |
| API, `POST` | `"colocate": [["person", "organization"], ["person#2", "address"]]` |
| API, `GET` | `colocate=person,organization;person%232,address` (`#` encoded as `%23`) |
| Command line | `--colocate person,organization`, repeatable |

A group has at least two instances, all used by the template, and an instance belongs to one
group only. At least one locality must be able to host every member: anywhere for an
address, in the homelands of some people for a person, and for an organization, anywhere if
the universe has an `organization_name` pattern, otherwise in the places of a canonical
organization. A group without a common locality is rejected before generation, rather than
failing at random depending on the seed.
