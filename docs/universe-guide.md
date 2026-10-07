# Universe guide

This guide explains how to write or extend a universe file. The examples come from
[`universes/lotr.yaml`](../universes/lotr.yaml).

## The ground rules

- **One universe, one file**: `universes/<id>.yaml`, where `<id>` equals `universe.id`.
- **Names and short labels only.** No quotes, no descriptions, no lore, no images. Every
  string is limited to 80 characters (200 for `universe.sources`).
- **No mass copy from a wiki.** Wiki content is often licensed under CC BY-SA, which is not
  compatible with the CC0 license of universe files. Write the data yourself, from the works.
- **Respect the declared scope** (`universe.sources.scope`). For instance, `lotr` covers the
  books only: no element that exists only in the films.
- **Mark invented elements** with `canon: false` (places, peoples, organizations, names,
  extension items you made up to enrich the pools).
- **Translations follow the reference translation** declared in `universe.sources.translations`.

## Workflow

```bash
uv run fakeverse validate universes/            # errors and warnings, with YAML paths and lines
uv run fakeverse validate --strict universes/   # warnings become errors (required for a merge)
uv run fakeverse coverage lotr                  # translation coverage and supported types
uv run fakeverse check-coherence lotr           # generate and check the coherence invariants
uv run fakeverse generate lotr person -n 3 --seed 42 --locale fr
```

Editors with YAML support (for instance VS Code with the YAML extension) offer autocompletion
and inline validation thanks to the first line of the file:

```yaml
# yaml-language-server: $schema=../schema/universe.schema.json
```

## Value types

### Localized text

A localized text is either a plain string, used for every locale, or a mapping from locale to
string. A mapping must contain the default locale of the universe; other locales are optional
and fall back to the default locale (the fallback is reported to users).

```yaml
name: Minas Tirith                                       # same in every language
name: { en: The Shire, fr: La Comté }                    # translated
```

Locales use the canonical BCP-47 form `language[-Script][-REGION]`: `en`, `fr`, `fr-CA`,
`zh-Hant-TW`. Write `fr-CA`, not `fr_CA` or `fr-ca`.

YAML is typed: write `name: "1984"` rather than `name: 1984`, which is a number and is
rejected. YAML anchors and aliases (`&name`, `*name`) are not allowed.

### Weighted items

Lists that are drawn at random (first names, family names, vocabularies) accept a short form
and a long form:

```yaml
first_names:
  - Bungo                                                        # short form
  - { en: Frodo, fr: Frodon }                                    # short form, translated
  - { value: { en: Samwise, fr: Samsagace }, gender: masculine, weight: 2 }   # long form
```

A mapping is in long form as soon as it has one of the keys `value`, `weight`, `gender` or
`canon`. The long form accepts:

| Key | Where | Default |
| --- | --- | --- |
| `value` | everywhere | required |
| `weight` | everywhere | 1 |
| `gender` (`masculine`, `feminine`, `neutral`) | `first_names` only | no gender |
| `canon` | `first_names` and `family_names` only | `true` |

Weights are integers from 1 to 1000: an item of weight 3 is drawn three times as often as an
item of weight 1. Places, peoples, organizations and extension items also take a `weight`.

## Sections

### `format` and `universe`

```yaml
format: 1

universe:
  id: lotr
  name: { en: The Lord of the Rings, fr: Le Seigneur des Anneaux }
  default_locale: en
  locales: [en, fr]
  sources:
    scope: "Books only: The Hobbit, The Lord of the Rings, The Silmarillion. No film-only elements."
    translations:
      fr: "Francis Ledoux; Pierre Alien for The Silmarillion"
  maintainers: [your-github-handle]
```

`maintainers` lists the GitHub handles responsible for the file; each one gets a line in
`.github/CODEOWNERS`.

### `generation` (optional)

```yaml
generation:
  organization_generated_ratio: 0.5    # share of generated organizations, in steps of 0.05
```

### `place_levels` (optional)

Labels of the three core place levels in this universe. Without them, the generic English
labels (Area, Subdivision, Locality) are used.

```yaml
place_levels:
  area: { en: Realm, fr: Royaume }
  subdivision: { en: Region, fr: Région }
  locality: { en: Town, fr: Ville }
```

### `places` (required)

Places form a three-level hierarchy: an `area` has no parent, a `subdivision` belongs to an
area, a `locality` belongs to a subdivision or directly to an area.

```yaml
places:
  - id: eriador
    level: area
    name: Eriador
  - id: shire
    level: subdivision
    parent: eriador
    name: { en: The Shire, fr: La Comté }
  - id: hobbiton
    level: locality
    parent: shire
    name: { en: Hobbiton, fr: Hobbitebourg }
    weight: 3
  - id: khazad-dum
    level: locality
    parent: eriador          # a locality directly in an area: its subdivision is null
    name: Khazad-dûm
```

Addresses are drawn from the localities, weighted by the weight of each **locality**. The weight
of an area or a subdivision does not change how often its localities appear; it only matters
for extension fields of the form `{ place: area }` or `{ place: subdivision }`.

A place can override some patterns for itself and its descendants (see
[Patterns](#patterns)):

```yaml
  - id: shire
    level: subdivision
    parent: eriador
    name: { en: The Shire, fr: La Comté }
    patterns:
      postal_code: "SH-{digits:3}"
```

### `peoples` (required)

A people carries naming rules and homelands. Homelands are places of any level; each one must
contain at least one locality. The addresses of a people are drawn from the
localities of its homelands.

```yaml
peoples:
  - id: hobbit
    name: Hobbit
    homelands: [shire, buckland, bree-land]
    weight: 4
    first_names:
      - { value: { en: Frodo, fr: Frodon }, gender: masculine }
      - { value: Lobelia, gender: feminine }
    family_names:
      - { en: Baggins, fr: Sacquet }
  - id: elf
    name: { en: Elf, fr: Elfe }
    homelands: [lindon, rivendell, lothlorien]
    name_format: "{first_name}"          # no family name
    first_names:
      - { value: Galadriel, gender: feminine }
```

- `name_format` defaults to `{first_name} {family_name}` when the people has family names,
  and to `{first_name}` otherwise.
- Patterns call the family name `family_name` (like the `family_names` list), while generated
  persons expose it as `last_name` (the Faker convention).
- Gender: when no gender is requested, a gender is drawn from the genders of the first names
  of the people, weighted by the sum of their weights; first names without gender go with any
  gender. A people whose first names have no gender produces persons with a null gender.
- Aim for at least 10 first names per people (a warning otherwise), and 30 for the main
  peoples.

### `organizations` (optional)

```yaml
organizations:
  - id: green-dragon
    name: { en: The Green Dragon, fr: Le Dragon Vert }
    kind: { en: Inn, fr: Auberge }
    places: [bywater]           # optional; any locality when omitted
```

Organizations can also be generated with the `organization_name` pattern; the share of
generated organizations is `generation.organization_generated_ratio`.

### `vocab` (optional)

Named lists of words or phrases used by patterns. Names are `snake_case`. Vocabulary entries
have no origin of their own: anything a pattern produces with them is `generated`.

```yaml
vocab:
  street_name:
    - { en: Old Mill, fr: du Vieux Moulin }
    - { en: Hill, fr: de la Colline }
  street_type:
    - { value: { en: Lane, fr: chemin }, weight: 3 }
```

The engine does not handle grammatical agreement. For languages that need it, use complete
phrases (as above, where the French entries carry their article: `du Vieux Moulin`,
`de la Colline`), or separate vocabularies by gender.

### Patterns

A pattern is a string with tokens between braces; everything else is literal, and `{{` and
`}}` produce literal braces.

| Token | Effect |
| --- | --- |
| `{vocab.NAME}` | Weighted draw from the vocabulary `NAME` |
| `{int:MIN-MAX}` | Uniform integer from MIN to MAX (0 to 10^9) |
| `{digits:N}` | N random digits (1 to 20) |
| `{letters:N}` | N random uppercase letters (1 to 20) |
| `{field}` | A field of the context (see below) |

Fields and vocabularies accept chained filters: `|slug` (no accents, lowercase, letters and
digits only), `|upper`, `|lower`, `|title`. For example `{first_name|slug}` turns `Éowyn` into
`eowyn`.

Patterns recognized by the core, and the context fields each one may use:

| Pattern | Used by | Fields | Overridable by a place |
| --- | --- | --- | --- |
| `street_address` | address | `locality`, `subdivision`, `area` | yes |
| `postal_code` | address | `locality`, `subdivision`, `area` | yes |
| `address_format` | address | the above, `street_address`, `postal_code` | yes |
| `phone` | person, organization | `locality`, `subdivision`, `area` | yes |
| `email` | person | `first_name`, `family_name`, `people`, `locality`, `subdivision`, `area` | no |
| `username` | person | same as `email` | no |
| `organization_name` | organization | `locality`, `subdivision`, `area` | no |
| `name_format` (in a people) | person | same as `email` | - |

```yaml
patterns:
  street_address:
    en: "{int:1-99} {vocab.street_name} {vocab.street_type}"
    fr: "{int:1-99}, {vocab.street_type} {vocab.street_name}"
  email: "{first_name|slug}.{family_name|slug}@{vocab.email_domain}"
```

Without `postal_code`, addresses have a null postal code. Without `address_format`, the
formatted address is `{street_address}, {locality}, {area}`. For a place, the override of the
nearest place (the place itself included) wins over the pattern of the universe.

**Empty fields.** A null field (an elf has no family name, a locality may have no
subdivision) renders as an empty string. The separators it leaves are then cleaned up, line
by line: `..` becomes `.`, `.@` and `-@` become `@`, repeated spaces are reduced, and spaces,
dots, commas and hyphens are trimmed at both ends of each line; empty lines disappear. So
`{first_name|slug}.{family_name|slug}@post.example` gives `elrond@post.example` for Elrond.
Patterns without an empty field are never modified. The pattern of a required value
(street address, formatted address, organization name, full name, extension field) must not
be able to render an empty string: it needs some text, a random token or a field that is never
null (`locality`, `area`, `first_name`...). An optional value (postal code, email, username,
phone) that renders empty is null.

Use email domains under the reserved `.example` top-level domain, so that generated
addresses never reach a real mailbox.

### `extensions` (optional)

Types specific to the universe. An extension has a `label` and exactly one of two forms. Its
id must not be a core type (`person`, `address`, `organization`), an atomic type
(`first_name`, `email`...) or `template`.

**`items` form**: a weighted draw from canonical entities. Every item declares the same
`fields` (localized texts or integers); `name` is reserved.

```yaml
extensions:
  weapon:
    label: { en: Weapon, fr: Arme }
    items:
      - id: sting
        name: { en: Sting, fr: Dard }
        fields:
          kind: { en: Sword, fr: Épée }
```

**`fields` form**: generation field by field, in declaration order. Field names are
`snake_case`.

```yaml
extensions:
  starship:
    label: { en: Starship, fr: Vaisseau }
    fields:
      name:     { pattern: { en: "{vocab.ship_adjective} {vocab.ship_noun}" } }
      model:    { vocab: ship_model }
      registry: { pattern: "{letters:2}-{digits:4}" }
      homeworld: { place: subdivision }
      crew:     { int: "1-5000" }
      operator: { people: true }
      call_sign: { pattern: "{registry}/{crew}" }   # sees the fields declared before it
```

## Validation

`fakeverse validate` reports every problem with its YAML path, line and code.

Errors (the file is rejected):

| # | Rule | Codes |
| --- | --- | --- |
| 1 | Valid YAML, known keys only, expected types; no YAML anchors or aliases | `yaml-syntax`, `duplicate-key`, `schema`, `yaml-alias` |
| 2 | `universe.id` equals the file name; every id matches `^[a-z0-9]+(-[a-z0-9]+)*$` | `id-mismatch`, `schema` |
| 3 | Ids are unique in each collection | `duplicate-id` |
| 4 | Parents, homelands, places, vocabularies and levels exist | `unknown-reference` |
| 5 | Parents have the right level | `place-hierarchy` |
| 6 | Homelands and organization places contain a locality | `no-locality` |
| 7 | Locales are declared; localized texts have the default locale | `locale-not-declared`, `missing-default-locale` |
| 8 | Locales are canonical BCP-47, declared once | `invalid-locale`, `duplicate-locale` |
| 9 | Patterns parse and use allowed fields; the pattern of a required value cannot render an empty string | `invalid-pattern`, `pattern-field-not-allowed`, `pattern-may-be-empty` |
| 10 | At least one locality and one people | `minimum-data` |
| 11 | No string over 80 characters (200 for `universe.sources`) | `string-too-long` |
| 12 | Files under 2 MB | `file-too-large` |
| 13 | Extensions are well formed and do not reuse a reserved id | `reserved-extension-id`, `reserved-field`, `inconsistent-fields` |

Warnings (errors with `--strict`):

| Code | Meaning |
| --- | --- |
| `translation-coverage` | A declared locale does not cover every localized text |
| `small-name-pool` | A people has fewer than 10 first names |
| `type-not-supported` | A core type cannot be generated with the data of the universe |

## Checklist for a new universe

- [ ] One file, `universes/<id>.yaml`, with at least one maintainer and their line in
      `.github/CODEOWNERS`.
- [ ] `sources.scope` states what is covered; `sources.translations` names the reference
      translation of each locale.
- [ ] Complete translations for every declared locale (`fakeverse coverage` at 100%).
- [ ] `fakeverse validate --strict` and `fakeverse check-coherence` pass.
- [ ] Only names and short labels; invented elements marked `canon: false`.
