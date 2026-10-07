# Fakeverse

[![CI](https://github.com/Kentrow/fakeverse/actions/workflows/ci.yml/badge.svg)](https://github.com/Kentrow/fakeverse/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/fakeverse)](https://pypi.org/project/fakeverse/)
[![Python](https://img.shields.io/pypi/pyversions/fakeverse)](https://pypi.org/project/fakeverse/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](https://github.com/Kentrow/fakeverse/blob/main/LICENSE)

Fakeverse generates fake data themed by works of fiction. Think
[Faker](https://faker.readthedocs.io/), but the people, addresses and organizations come from
a fictional world, and they are **consistent with each other**: a hobbit lives in a town of
the Shire, the town is in the right region, and the email is built from the name.

For instance, `lotr.one("person", people="hobbit", seed=7)` gives:

```json
{
  "first_name": "Gilly",
  "last_name": "Took",
  "full_name": "Gilly Took",
  "gender": "feminine",
  "people": "Hobbit",
  "address": {
    "street_address": "7 Smithy Street",
    "postal_code": "SH-594",
    "locality": "Oatbarton",
    "subdivision": "The Shire",
    "area": "Eriador",
    "formatted": "7 Smithy Street\nOatbarton SH-594\nThe Shire, Eriador"
  },
  "email": "gilly.took@post.example",
  "username": "gilly972",
  "phone": "+35 872 9950"
}
```

- **Coherent**: generated values respect the relations between peoples, places and names.
- **Multilingual**: every universe is translated, following a reference translation, and
  fallbacks to another language are reported.
- **Reproducible**: the same seed and the same data version always give the same result.
- **Easy to contribute**: one YAML file per universe, validated automatically.
- **Everywhere**: Python package, Faker provider, command line and HTTP API.

## Universes

| Id | Universe | Scope | Locales |
|---|---|---|---|
| `lotr` | The Lord of the Rings | The books only, no film adaptations | English, French |
| `starwars` | Star Wars | The Disney canon (2014 and later) | English, French |

New universes are welcome: see [Contributing](#contributing).

## Installation

```bash
pip install fakeverse            # package and command line
pip install "fakeverse[faker]"   # with the Faker provider
pip install "fakeverse[api]"     # with the HTTP API
```

Fakeverse needs Python 3.12 or later.

## Python package

```python
from fakeverse import Fakeverse

fv = Fakeverse()
lotr = fv.universe("lotr")

result = lotr.generate("first_name", count=3, seed=42)
result.items  # ['Andwise', 'Orodreth', 'Dáin']
result.meta.seed  # 42

lotr.one("full_name", seed=1, gender="feminine")  # 'Dís'
lotr.generate("person", count=5, people="hobbit")  # five hobbits, no duplicates
lotr.generate("weapon", count=2, seed=3).items  # a type specific to the universe
# [{'name': 'Glamdring', 'kind': 'Sword'}, {'name': 'Aeglos', 'kind': 'Spear'}]

fv.universe("lotr", locale="fr").generate("full_name", count=3, seed=42).items
# ['Flói', 'Hugo Goold', 'Fréaláf']
```

Templates combine several types in one row. Leaves that reference the same instance describe
the same entity, and `colocate` puts instances in the same locality:

```python
lotr.template(
    {
        "name": "person.full_name",
        "employer": "organization.name",
        "town": "person.address.locality",
    },
    count=2,
    seed=7,
    colocate=[["person", "organization"]],
).items
# [{'name': 'Théodred', 'employer': 'The Wild Boar', 'town': 'Aldburg'},
#  {'name': 'Náli', 'employer': 'The Old Mill', 'town': 'Erebor'}]
```

Types: the composites `person`, `address` and `organization`, their projections
(`first_name`, `last_name`, `full_name`, `email`, `username`, `phone`, `street_address`,
`postal_code`, `locality`, `subdivision`, `area`, `organization_name`), and the types specific
to each universe. Options include `unique` (on by default, as far as the pool allows) and
`explain`, which tells for each value whether it comes from the works (`canon`) or was made
up (`generated`).

[How generation works](https://github.com/Kentrow/fakeverse/blob/main/docs/generation.md)
describes types, seeds, locales, uniqueness and templates in detail.

## Faker provider

```python
from faker import Faker
from fakeverse.faker import FakeverseProvider

fake = Faker("fr_FR")
fake.add_provider(FakeverseProvider)

fake.fakeverse("lotr").person()
fake.fakeverse("lotr").first_name(gender="feminine")
fake.fakeverse("lotr").generate("weapon")
fake.fakeverse("lotr").template({"name": "person.full_name"})
fake.fakeverse("lotr").unique.first_name()  # never twice the same value
```

`Faker.seed()` makes sequences reproducible. The locale of Faker is used when the universe
supports its language, and the default locale of the universe otherwise;
`fake.fakeverse("lotr", strict_locale=True)` raises an error instead.

## Command line

```bash
fakeverse generate lotr person -n 3 --seed 42 --locale fr
fakeverse generate lotr full_name -n 100 --format csv > names.csv
echo '{"name": "person.full_name", "employer": "organization.name"}' \
  | fakeverse template lotr - -n 10 --format ndjson --colocate person,organization
fakeverse info
```

`fakeverse --help` lists every command. Contributors also use `fakeverse validate`,
`fakeverse coverage` and `fakeverse check-coherence`.

## HTTP API

```bash
pip install "fakeverse[api]"
uvicorn fakeverse.api.app:app --no-access-log

curl "http://localhost:8000/v1/universes/lotr/generate/person?count=3&seed=42&locale=fr"
curl "http://localhost:8000/v1/universes/starwars/generate/starship?count=10&format=csv"
curl -X POST "http://localhost:8000/v1/universes/lotr/generate" \
  -H "Content-Type: application/json" \
  -d '{"template": {"name": "person.full_name", "town": "person.address.locality"}, "count": 10}'
```

The API supports JSON, NDJSON and CSV, reports errors in the RFC 9457 format, applies rate
limiting, and sets HTTP cache headers on requests with a seed. The interactive documentation is served at `/docs`. See the
[API reference](https://github.com/Kentrow/fakeverse/blob/main/docs/api.md) and the
[deployment guide](https://github.com/Kentrow/fakeverse/blob/main/docs/deployment.md), which
covers the Docker image.

## Contributing

New universes, names, translations and fixes are welcome. Read the
[contributing guide](https://github.com/Kentrow/fakeverse/blob/main/CONTRIBUTING.md) and the
[universe guide](https://github.com/Kentrow/fakeverse/blob/main/docs/universe-guide.md).

## License

- Code: [MIT](https://github.com/Kentrow/fakeverse/blob/main/LICENSE).
- Universe files (`universes/`):
  [CC0-1.0](https://github.com/Kentrow/fakeverse/blob/main/universes/LICENSE).

These licenses cover only the contributions of the Fakeverse project (data structure, patterns,
generated vocabulary and original content), not the names and trademarks of the original works.
See [NOTICE](https://github.com/Kentrow/fakeverse/blob/main/NOTICE). Rights holders can follow
the [takedown procedure](https://github.com/Kentrow/fakeverse/blob/main/TAKEDOWN.md).

## Disclaimer

Fakeverse is an independent, non-commercial open source project. It is not affiliated with,
endorsed by, or sponsored by any rights holder of the works it draws inspiration from. All names,
characters, places and trademarks belong to their respective owners. Universe files contain only
short names and labels; no text, quotes or images from the original works.

## Code of conduct

This project follows the
[Contributor Covenant 2.1](https://github.com/Kentrow/fakeverse/blob/main/CODE_OF_CONDUCT.md).
