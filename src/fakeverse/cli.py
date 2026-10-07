"""Command line interface of Fakeverse."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from fakeverse import __version__
from fakeverse.capabilities import compute_capabilities
from fakeverse.coherence import check_universe
from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.errors import FakeverseError, InvalidTemplate, UniverseValidationError
from fakeverse.fakeverse import Fakeverse, GenerationResult
from fakeverse.formats import OutputFormat, check_format, render
from fakeverse.loader import (
    LoadResult,
    embedded_universes_dir,
    find_universe_files,
    load_directory,
    load_file,
)
from fakeverse.locale import resolve
from fakeverse.model import UniverseFile, universe_json_schema
from fakeverse.validation import format_path, locale_coverage

app = typer.Typer(
    name="fakeverse",
    help="Coherent fake data generator themed by fictional universes.",
    no_args_is_help=True,
    add_completion=False,
)
schema_app = typer.Typer(help="JSON Schema of the universe file format.", no_args_is_help=True)
app.add_typer(schema_app, name="schema")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"fakeverse {__version__}")
        raise typer.Exit


@app.callback()
def main(
    ctx: typer.Context,
    universes_dir: Annotated[
        Path | None,
        typer.Option(
            "--universes-dir",
            exists=True,
            file_okay=False,
            dir_okay=True,
            help="Use the universes of this directory instead of the embedded ones.",
        ),
    ] = None,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the package version and exit.",
        ),
    ] = False,
) -> None:
    """Coherent fake data generator themed by fictional universes."""
    ctx.obj = universes_dir


def _universes_dir(ctx: typer.Context) -> Path:
    directory: Path | None = ctx.obj
    return directory if directory is not None else embedded_universes_dir()


def _fail(message: str) -> typer.Exit:
    typer.echo(message, err=True)
    return typer.Exit(code=1)


@app.command()
def validate(
    ctx: typer.Context,
    paths: Annotated[
        list[Path] | None,
        typer.Argument(
            exists=True,
            help="Universe files or directories. Default: the --universes-dir directory, or the "
            "embedded universes.",
            show_default=False,
        ),
    ] = None,
    strict: Annotated[bool, typer.Option("--strict", help="Treat warnings as errors.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Validate universe files. Exit code 1 when a file is invalid."""
    files = find_universe_files(paths or [_universes_dir(ctx)])
    results = [load_file(path) for path in files]
    if as_json:
        typer.echo(json.dumps(_validation_json(results, strict=strict), indent=2))
    elif not results:
        typer.echo("No universe file found.", err=True)
    else:
        for result in results:
            _print_result(result, strict=strict)
        invalid = sum(not result.is_valid(strict=strict) for result in results)
        typer.echo(f"{len(results)} file(s) checked, {invalid} invalid.")
    if not all(result.is_valid(strict=strict) for result in results):
        raise typer.Exit(code=1)


def _print_result(result: LoadResult, *, strict: bool) -> None:
    status = "valid" if result.is_valid(strict=strict) else "invalid"
    counts = f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)"
    typer.echo(f"{result.path}: {status} ({counts})")
    for issue in result.issues:
        typer.echo(f"  {issue.severity}: {issue.format(with_file=False)}")


def _validation_json(results: list[LoadResult], *, strict: bool) -> dict[str, Any]:
    return {
        "valid": all(result.is_valid(strict=strict) for result in results),
        "strict": strict,
        "files": [
            {
                "path": str(result.path),
                "universe": result.universe.universe.id if result.universe else None,
                "valid": result.is_valid(strict=strict),
                "errors": len(result.errors),
                "warnings": len(result.warnings),
                "issues": [issue.to_dict() for issue in result.issues],
            }
            for result in results
        ],
    }


def _load_universes(ctx: typer.Context) -> dict[str, UniverseFile]:
    try:
        return load_directory(_universes_dir(ctx))
    except UniverseValidationError as exc:
        raise _fail(str(exc)) from exc


@app.command()
def coverage(
    ctx: typer.Context,
    universe: Annotated[
        str | None, typer.Argument(help="Universe id. Default: every universe.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Report translation coverage by locale and supported types."""
    universes = _load_universes(ctx)
    if universe is not None:
        if universe not in universes:
            raise _fail(f"Unknown universe '{universe}'.")
        universes = {universe: universes[universe]}
    reports = [_coverage_report(data) for data in universes.values()]
    if as_json:
        typer.echo(json.dumps(reports, indent=2, ensure_ascii=False))
        return
    if not reports:
        typer.echo("No universe found.", err=True)
    for report in reports:
        _print_coverage(report)


def _coverage_report(universe: UniverseFile) -> dict[str, Any]:
    meta = universe.universe
    capabilities = compute_capabilities(universe)
    return {
        "id": meta.id,
        "name": resolve(meta.name, meta.default_locale, meta.default_locale).value,
        "locale_coverage": {
            locale: {"ratio": round(ratio, 4), "missing": [format_path(p) for p in missing]}
            for locale, (ratio, missing) in locale_coverage(universe).items()
        },
        "capabilities": {
            "core": list(capabilities.core),
            "unsupported": capabilities.unsupported,
            "extensions": [
                {
                    "id": ext.id,
                    "label": resolve(ext.label, meta.default_locale, meta.default_locale).value,
                    "fields": list(ext.fields),
                }
                for ext in capabilities.extensions
            ],
        },
    }


def _print_coverage(report: dict[str, Any]) -> None:
    typer.echo(f"{report['id']} - {report['name']}")
    typer.echo("  Translation coverage:")
    for locale, entry in report["locale_coverage"].items():
        missing = entry["missing"]
        suffix = f" ({len(missing)} missing)" if missing else ""
        typer.echo(f"    {locale:<10} {entry['ratio']:7.1%}{suffix}")
        for path in missing:
            typer.echo(f"      - {path}")
    capabilities = report["capabilities"]
    typer.echo(f"  Core types: {', '.join(capabilities['core']) or 'none'}")
    for type_id, reason in capabilities["unsupported"].items():
        typer.echo(f"  Not supported: {type_id} ({reason})")
    for ext in capabilities["extensions"]:
        typer.echo(f"  Extension: {ext['id']} ({', '.join(ext['fields'])})")


def _fakeverse(ctx: typer.Context) -> Fakeverse:
    try:
        return Fakeverse(_universes_dir(ctx))
    except UniverseValidationError as exc:
        raise _fail(str(exc)) from exc


CountOption = Annotated[int, typer.Option("-n", "--count", min=1, help="Number of items.")]
SeedOption = Annotated[
    int | None, typer.Option(help="Seed (0 to 2^63 - 1); random when omitted.", show_default=False)
]
LocaleOption = Annotated[
    str | None, typer.Option(help="BCP-47 locale; the default locale of the universe when omitted.")
]
UniqueOption = Annotated[
    bool | None,
    typer.Option(
        "--unique/--no-unique",
        help="Default: avoid duplicates while the pool allows it. --unique: fail when the pool "
        "runs out. --no-unique: allow duplicates.",
        show_default=False,
    ),
]
ExplainOption = Annotated[
    bool, typer.Option("--explain", help="Show the origin, locale and fallback of each value.")
]
FormatOption = Annotated[OutputFormat, typer.Option("--format", help="Output format.")]


def _emit(result: GenerationResult, output: OutputFormat, *, explain: bool) -> None:
    text = render(result, output, explain=explain)
    if result.meta.seed_generated and output is not OutputFormat.JSON:
        typer.echo(f"Seed: {result.meta.seed}", err=True)
    typer.echo(text, nl=False)


@app.command()
def generate(
    ctx: typer.Context,
    universe: Annotated[str, typer.Argument(metavar="UNIVERSE", help="Universe id.")],
    type_id: Annotated[str, typer.Argument(metavar="TYPE", help="Core or extension type.")],
    count: CountOption = 1,
    seed: SeedOption = None,
    locale: LocaleOption = None,
    unique: UniqueOption = None,
    explain: ExplainOption = False,
    gender: Annotated[
        str | None, typer.Option(help="masculine, feminine or neutral (person types).")
    ] = None,
    people: Annotated[str | None, typer.Option(help="People id (person types).")] = None,
    output: FormatOption = OutputFormat.JSON,
) -> None:
    """Generate items of a type to stdout."""
    fakeverse = _fakeverse(ctx)
    try:
        check_format(output, explain=explain)
        result = fakeverse.universe(universe, locale).generate(
            type_id, count, seed, unique=unique, explain=explain, gender=gender, people=people
        )
        _emit(result, output, explain=explain)
    except FakeverseError as exc:
        raise _fail(f"Error ({exc.slug}): {exc}") from exc


@app.command()
def template(
    ctx: typer.Context,
    universe: Annotated[str, typer.Argument(metavar="UNIVERSE", help="Universe id.")],
    file: Annotated[
        str, typer.Argument(metavar="FILE", help="JSON template file, or - for stdin.")
    ],
    count: CountOption = 1,
    seed: SeedOption = None,
    locale: LocaleOption = None,
    unique: UniqueOption = None,
    explain: ExplainOption = False,
    output: FormatOption = OutputFormat.JSON,
    colocate: Annotated[
        list[str] | None,
        typer.Option(
            "--colocate",
            help="Instances sharing one locality, e.g. 'person,organization'. Repeatable.",
            show_default=False,
        ),
    ] = None,
) -> None:
    """Generate rows from a JSON template to stdout."""
    try:
        if file == "-":
            source = typer.get_text_stream("stdin").read()
        else:
            source = Path(file).read_text(encoding="utf-8")
        document = json.loads(source)
    except (OSError, ValueError, RecursionError) as exc:
        raise _fail(f"Cannot read template: {exc}") from exc
    fakeverse = _fakeverse(ctx)
    try:
        check_format(output, explain=explain)
        groups = [[member.strip() for member in group.split(",")] for group in colocate or []]
        result = fakeverse.universe(universe, locale).template(
            document, count, seed, unique=unique, explain=explain, colocate=groups
        )
        _emit(result, output, explain=explain)
    except InvalidTemplate as exc:
        details = "".join(f"\n  {error['path'] or '/'}: {error['reason']}" for error in exc.errors)
        raise _fail(f"Error ({exc.slug}): {exc}{details}") from exc
    except FakeverseError as exc:
        raise _fail(f"Error ({exc.slug}): {exc}") from exc


@app.command("check-coherence")
def check_coherence(
    ctx: typer.Context,
    universe: Annotated[
        str | None, typer.Argument(help="Universe id. Default: every universe.")
    ] = None,
    count: Annotated[
        int, typer.Option("-n", "--count", min=1, help="Items per type and locale.")
    ] = 200,
    seed: Annotated[int, typer.Option(help="Seed used for every generation.")] = 0,
) -> None:
    """Generate items of every supported type in every locale and check the invariants."""
    fakeverse = _fakeverse(ctx)
    ids = [info.id for info in fakeverse.universes()]
    if universe is not None:
        if universe not in ids:
            raise _fail(f"Unknown universe '{universe}'.")
        ids = [universe]
    if not ids:
        typer.echo("No universe found.", err=True)
    failed = False
    for universe_id in ids:
        violations = check_universe(fakeverse, universe_id, count=count, seed=seed)
        status = "OK" if not violations else f"{len(violations)} violation(s)"
        typer.echo(f"{universe_id}: {status}")
        for violation in violations:
            typer.echo(f"  {violation.format()}")
        failed = failed or bool(violations)
    if failed:
        raise typer.Exit(code=1)


@schema_app.command("export")
def schema_export() -> None:
    """Write the JSON Schema of the universe file format to stdout."""
    typer.echo(json.dumps(universe_json_schema(), indent=2, ensure_ascii=False))


@app.command()
def info() -> None:
    """Show the package version, the engine revision and the embedded universes."""
    directory = embedded_universes_dir()
    embedded = (
        [path.stem for path in find_universe_files([directory])] if directory.is_dir() else []
    )
    typer.echo(f"fakeverse {__version__}")
    typer.echo(f"Engine revision: {ENGINE_REVISION}")
    typer.echo(f"Embedded universes: {', '.join(embedded) or 'none'}")
