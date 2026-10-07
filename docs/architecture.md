# Architecture

This page is for contributors: how the code is organized, and the few design rules that keep
the output reproducible. The behavior users can rely on is described in
[How generation works](generation.md).

## Goals

- **Coherent data**: a generated value agrees with the others (a person lives in the homelands
  of their people, an address in the region it names).
- **Reproducible output**: the same request, seed and data give the same result, on every
  platform and every supported Python version.
- **A generic engine**: everything specific to a universe lives in its YAML file; no code in
  `src/` knows about a particular universe.
- **One file per universe**, easy to review and to contribute to.

## Layout

```text
src/fakeverse/
├── model/            Pydantic models of the universe file format (source of the JSON Schema)
├── loader.py         Reading of universe files (safe YAML, line numbers, duplicate keys)
├── validation.py     Semantic validation rules, with YAML paths and stable codes
├── types.py          The core taxonomy: composite types, their fields, atomic types
├── capabilities.py   Types a universe supports, derived from its data
├── hierarchy.py      Navigation in the place hierarchy (areas, subdivisions, localities)
├── locale.py         Locale normalization and fallback chain
├── patterns/         Pattern DSL: parser (at load time) and renderer (at generation time)
├── rng.py            The only source of randomness, and seed derivation
├── engine/
│   ├── index.py      Compiled form of a universe: weighted pools, parsed patterns
│   ├── generators/   One generator per core type, plus extension types
│   ├── template.py   Template compilation and rendering of rows
│   ├── colocate.py   Colocation groups of template instances
│   ├── unique.py     Uniqueness of the items of a response
│   ├── explain.py    Values with their origin, locale and fallback
│   └── revision.py   ENGINE_REVISION
├── fakeverse.py      Public Python API: Fakeverse, UniverseGenerator, GenerationResult
├── coherence.py      Coherence invariants, used by check-coherence and the property tests
├── formats.py        JSON, NDJSON and CSV output
├── releases.py       releases.toml and SemVer helpers
├── cli.py            Command line (Typer)
├── faker.py          Faker provider (extra faker)
└── api/              HTTP API (extra api, FastAPI)
```

## From a file to a value

1. **Loading.** `loader.py` reads a file with the safe YAML loader, refuses anchors and
   aliases, and keeps the line of every YAML path. `model/` checks the structure, then
   `validation.py` the semantic rules (references, hierarchy, locales, patterns...). Every
   problem is reported with its path, line and code; nothing is generated from an invalid file.
2. **Compilation.** `engine/index.py` turns a valid universe into an index, once: pools with
   cumulative weights in file order, parsed patterns, the localities of each homeland, the
   capabilities. Generation then does no I/O and no parsing.
3. **Generation.** For each item, `fakeverse.py` derives a seed and hands a `Draw` (index,
   random generator, locale) to the generator of the type. Generators draw from the pools and
   render patterns, producing nodes that carry each value with its origin and locale.
4. **Output.** `engine/explain.py` renders nodes raw or explained, and `formats.py` serializes
   them. The CLI, the Faker provider and the API are thin layers over the Python API.

## Determinism

The output is a contract, so randomness is tightly controlled:

- `rng.Rng` only calls `getrandbits` of `random.Random`, whose output is stable across Python
  versions, and implements every other primitive on top of it (`below`, `weighted_index`...).
- The seed of an item is derived with BLAKE2b from the canonical JSON of
  `[ENGINE_REVISION, universe, kind, locale, options, seed, index]`, plus the attempt number
  when uniqueness retries an item. `kind` is the type, or for a template the instance
  (`template:person#2`) or the colocation group. Items are therefore independent of each other,
  and of `count`.
- Lists keep the order of the universe file. Sets, `hash()`, the clock and the global `random`
  module are banned from the generation path: ruff and `tests/unit/test_determinism_guard.py`
  enforce it.
- Golden files (`tests/golden/`) record the output of reference requests. A change that alters
  them must increment `ENGINE_REVISION`; `pytest --update-goldens` rewrites them.

## The API

`api/app.py` builds the FastAPI application from `Settings` (`FAKEVERSE_*` variables).
`api/snapshots.py` loads one universe set per data version; `api/routes.py` validates the
parameters and runs the generation, in a thread pool for templates, under a work budget.
Middlewares add rate limiting (an in-memory token bucket per client IP, `api/ratelimit.py`),
the JSON access log, metrics and CORS. Errors are RFC 9457 problems (`api/problems.py`), and
responses with a seed are cacheable (`api/cache.py`).

## Tests

| Directory | Content |
| --- | --- |
| `tests/unit/` | Unit tests of each module, the CLI, the Faker provider and the scripts |
| `tests/api/` | The HTTP API through its test client, including fuzzing of the parameters |
| `tests/property/` | Hypothesis tests: coherence invariants for any seed, robustness of validation |
| `tests/golden/` | Reference outputs that detect any change of the generated values |
| `tests/fixtures/` | The `test-world` universe, a minimal valid file, one invalid file per rule |
| `tests/bench/` | A benchmark, run by the CI for information |
