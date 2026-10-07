# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Changes to `ENGINE_REVISION` are always listed, since they change generated output. See
[CONTRIBUTING.md](CONTRIBUTING.md#versioning) for the versioning policy.

## [Unreleased]

## [0.1.0] - 2026-10-07

First release. `ENGINE_REVISION` = 1.

### Added

- Universes `lotr` (The Lord of the Rings, books only) and `starwars` (Star Wars, Disney
  canon), in English and French. French names follow the reference translations.
- Core types `person`, `address` and `organization`, their atomic projections, and extension
  types declared by each universe (`weapon`, `starship`...).
- Deterministic generation: the same seed, data version and request always give the same
  result, stable by prefix; a random seed is drawn and returned when none is given.
- Locales in BCP-47 form, with normalization and reported fallbacks.
- Uniqueness by default, as far as the pool allows, with duplicates counted in
  `meta.duplicates`; `unique=true` is strict and `unique=false` allows duplicates.
- Explain mode: origin (`canon` or `generated`), locale and fallback of each value.
- Templates: rows combining several types, with shared instances, and colocation groups of
  instances located in the same locality.
- Python API: `Fakeverse`, `UniverseGenerator`, `GenerationResult`.
- Faker provider (extra `faker`): `fake.fakeverse(universe)`, with one method per core type,
  `generate`, `template` and `.unique`.
- Command line: `generate`, `template`, `info`, and for contributors `validate`, `coverage`,
  `check-coherence` and `schema export`; JSON, NDJSON and CSV output.
- HTTP API (extra `api`): every endpoint of `/v1`, JSON, NDJSON and CSV formats, template
  generation by `POST` or by a cacheable `GET`, RFC 9457 problems whose types lead to their
  documentation, per-client rate limiting with trusted proxies, HTTP caching with ETag,
  several data versions, configuration by environment variables, JSON access logs and
  optional Prometheus metrics.
- Docker image of the API, with the data of every release of the current engine revision.
- Universe file format with a JSON Schema (`schema/universe.schema.json`), and validation with
  YAML paths, line numbers and stable error codes.
- Documentation: universe guide, how generation works, API reference, API problems,
  deployment guide, architecture, security policy and release procedure.
- Releases with signed provenance: PyPI distributions with PEP 740 attestations, and a
  multi-platform image (`linux/amd64`, `linux/arm64`) with an SBOM.
- Hardening: YAML anchors and aliases are refused in universe files, invalid encodings and
  excessive nesting are reported instead of crashing; in the API, template generation runs
  off the event loop with a work budget, bodies are read as a stream and capped at 64 KB,
  IPv6 clients are rate limited per /64 network, and every `X-Forwarded-For` header is taken
  into account.

[Unreleased]: https://github.com/Kentrow/fakeverse/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Kentrow/fakeverse/releases/tag/v0.1.0
