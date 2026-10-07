# Contributing to Fakeverse

Thanks for your interest! Fakeverse welcomes two kinds of contributions: **universe data**
(new universes, more names, translations, fixes) and **code** (engine, CLI, Faker provider,
API). Both follow the rules below.

By participating, you agree to follow the [code of conduct](CODE_OF_CONDUCT.md).

## Content rules for universe files

Universe files are published under CC0-1.0 and served by a public API. To keep the project
respectful of the works it draws inspiration from, and legally sound:

- **Names and short labels only.** No quotes, no descriptions, no lore, no images. Validation
  rejects any string longer than 80 characters (200 under `universe.sources`).
- **No mass copy from a wiki.** Wikis are often licensed under CC BY-SA, which is not
  compatible with CC0. Gather names yourself, from the works.
- **Respect the scope of the universe** (`universe.sources.scope`). For instance, `lotr`
  covers the books only: no element that exists only in the film adaptations.
- **Follow the reference translation** declared for each locale in
  `universe.sources.translations`.
- **Mark invented elements** with `canon: false`: places, peoples, organizations, names or
  extension items added to enrich the pools.
- Canon debates are settled within the declared scope, by the maintainers of the universe.

The format is described in the [universe guide](docs/universe-guide.md).

## Workflow

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv sync --all-extras                              # install everything
uv run pre-commit install                         # check every commit and its message
uv run fakeverse validate --strict universes/     # validate the universe files
uv run fakeverse check-coherence                  # check the coherence of generated data
uv run fakeverse coverage lotr                    # translation coverage and supported types
uv run fakeverse generate lotr person -n 3 --seed 42 --locale fr   # look at the result
uv run pytest                                     # run the tests
uv run pre-commit run --all-files                 # lint, format, type check, spelling...
```

- **One pull request per universe.** Do not mix changes to several universes, or universe
  data and code, in one pull request.
- **Commits** follow Conventional Commits and are signed off (see [Commits](#commits)).
- **Tests**: every feature comes with its tests; the CI must stay green.
- **Changelog**: describe your change for users in the `[Unreleased]` section of
  `CHANGELOG.md`, under the right heading (`Added`, `Changed`, `Deprecated`, `Removed`,
  `Fixed` or `Security`, as in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)).
  Do not change version numbers: releases take care of them.

### Adding a universe

1. Open a "New universe" issue to agree on the scope and the id.
2. Create `universes/<id>.yaml`, starting from the [universe guide](docs/universe-guide.md).
3. Declare at least one maintainer in `universe.maintainers`, and add the matching line to
   `.github/CODEOWNERS` (`/universes/<id>.yaml @handle`). A test checks it.
4. Translate every value for the default locale and for each declared locale
   (`fakeverse coverage` at 100%).
5. Make sure `fakeverse validate --strict` and `fakeverse check-coherence` pass.

### Changing the code

For a large change, open an issue first to discuss it.

- **Generic engine.** No code specific to a universe in `src/`: everything that belongs to a
  universe is expressed in its YAML file. If a universe needs something the format cannot
  express, propose an extension of the format.
- **Determinism.** Randomness goes through `fakeverse.rng` only. In the generation path, do not
  use the `random` module, the `choice`, `choices`, `randint`, `randrange`, `shuffle`,
  `sample` or `random` methods, `hash()`, iteration over a `set` or a `frozenset`, the clock,
  `uuid4` or `secrets` (`fakeverse.rng.random_seed()` draws missing seeds). Ruff and a test
  enforce these rules.
- **Generation contract.** The output of a generation is a contract: the same seed, data
  version and request always give the same result. If your change alters the output for
  identical inputs and data, the golden tests fail. Then increment `ENGINE_REVISION` in
  `src/fakeverse/engine/revision.py`, note it in `CHANGELOG.md`, and regenerate the goldens
  with `uv run pytest --update-goldens`.
- **Language and style.** Code, comments, docstrings, error messages and documentation are
  written in English. In prose, use a simple hyphen `-` rather than an em dash.
- **Typing.** `mypy --strict` must pass on `src/`.

[How generation works](docs/generation.md) describes the behavior the engine guarantees, and
the [architecture](docs/architecture.md) how the code is organized.

## Commits

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/):

```text
feat(universes): add the dwarves of the Iron Hills

Optional body, explaining what and why.

Signed-off-by: Your Name <you@example.com>
```

- **Header**: `type(scope): description`, at most 100 characters, without a final period.
  Types: `feat` (a new feature or new data), `fix` (a bug or a wrong name), `docs`, `test`,
  `refactor`, `perf`, `build`, `ci`, `chore`, `style` and `revert`. The scope is optional,
  for instance `universes`, `engine`, `api`, `cli` or `faker`.
- **Breaking changes** add `!` after the type or scope (`feat(api)!: ...`) and explain the
  change in a `BREAKING CHANGE:` paragraph.
- **Sign-off.** Fakeverse uses the [Developer Certificate of Origin](https://developercertificate.org/)
  instead of a CLA. Sign off every commit with `git commit -s` to certify that you wrote it or
  have the right to submit it under the licenses of the project.

The `commit-msg` hook installed by `pre-commit install` checks your messages, and the CI checks
every commit of a pull request. Pull requests are squashed when merged: their title becomes the
header of the commit, so it follows the same format.

## Versioning

Fakeverse follows [Semantic Versioning](https://semver.org/). The version of the package is
also the version of its data (`data_version`), so a change of the generated output for the
same request is a change of version:

| Change | From 1.0.0 | Before 1.0.0 |
| --- | --- | --- |
| Breaking change of the HTTP API, the universe file format or the Python API; increment of `ENGINE_REVISION` | MAJOR | MINOR |
| New feature, new type, or any change of `universes/` (it changes the output for a seed) | MINOR | MINOR |
| Fix that does not change any output | PATCH | PATCH |

Before 1.0.0, the API and the formats may still change in a MINOR release; the changelog
always says so.

## Releases

Releases are cut by the maintainers, as described in [RELEASING.md](RELEASING.md).

## Licenses

- Code: [MIT](LICENSE).
- Universe files: [CC0-1.0](universes/LICENSE).

These licenses cover the contributions of the project, not the names and trademarks of the
original works; see [NOTICE](NOTICE).
