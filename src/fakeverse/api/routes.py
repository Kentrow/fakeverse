"""Endpoints of the API."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Path, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from fakeverse import __version__
from fakeverse.api.cache import NO_STORE, cache_control, etag, matches
from fakeverse.api.formats import generation_response, negotiate
from fakeverse.api.metrics import Metrics
from fakeverse.api.problems import Problem, invalid_parameter
from fakeverse.api.ratelimit import RateLimiter
from fakeverse.api.schemas import (
    CACHEABLE_GENERATION,
    GENERATION,
    Health,
    Meta,
    Types,
    UniverseDetail,
    UniverseList,
    problems,
)
from fakeverse.api.settings import Settings
from fakeverse.api.snapshots import SnapshotStore
from fakeverse.engine.colocate import compile_with_groups
from fakeverse.engine.generators import resolve_generator
from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.engine.template import MAX_DEPTH
from fakeverse.errors import FakeverseError, LocaleNotSupported, TypeNotSupported
from fakeverse.fakeverse import GenerationResult, UniverseGenerator
from fakeverse.formats import OutputFormat, check_format
from fakeverse.rng import MAX_SEED
from fakeverse.types import ATOMIC_ALIASES, COMPOSITES, DEFAULT_PLACE_LEVEL_LABELS, PLACE_LEVELS
from fakeverse.validation import locale_coverage

MAX_BODY: Final[int] = 64 * 1024
MAX_ENCODED_TEMPLATE: Final[int] = (MAX_BODY + 2) // 3 * 4
TEMPLATE_BUDGET_FACTOR: Final[int] = 5
"""A template request generates at most ``max_count x 5`` instances."""

DISCLAIMER: Final[str] = (
    "Fakeverse is an independent, non-commercial open source project. It is not affiliated "
    "with, endorsed by, or sponsored by any rights holder of the works it draws inspiration "
    "from. All names, characters, places and trademarks belong to their respective owners."
)

GENERATE_PARAMS: Final[frozenset[str]] = frozenset(
    {"count", "seed", "locale", "data_version", "unique", "explain", "format", "gender", "people"}
)
LISTING_PARAMS: Final[frozenset[str]] = frozenset({"locale", "data_version"})


@dataclass(slots=True)
class AppState:
    """What the endpoints share."""

    settings: Settings
    store: SnapshotStore
    limiter: RateLimiter | None
    metrics: Metrics | None


router = APIRouter(prefix="/v1")

Locale = Annotated[str | None, Query(description="BCP-47 locale, e.g. fr or fr-FR.")]
DataVersion = Annotated[
    str | None, Query(description="Data version (SemVer); the most recent by default.")
]


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.fakeverse
    return state


def reject_unknown(request: Request, allowed: frozenset[str]) -> None:
    unknown = sorted(key for key in request.query_params if key not in allowed)
    if unknown:
        raise invalid_parameter(
            [{"name": key, "location": "query", "message": "Unknown parameter"} for key in unknown]
        )


def record(request: Request, **fields: object) -> None:
    """Remember fields of the request for the access log."""
    request.state.log = {**getattr(request.state, "log", {}), **fields}


@router.get("/health", summary="Health check", response_model=Health)
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/meta",
    summary="Versions, limits and disclaimer",
    response_model=Meta,
    responses=problems(422, 429),
)
def meta(request: Request) -> dict[str, Any]:
    reject_unknown(request, frozenset())
    state = app_state(request)
    return {
        "package_version": __version__,
        "engine_revision": ENGINE_REVISION,
        "data_versions": state.store.versions,
        "default_data_version": state.store.default_version,
        "limits": {
            "max_count": state.settings.max_count,
            "max_template_leaves": state.settings.max_template_leaves,
            "max_template_depth": MAX_DEPTH,
        },
        "disclaimer": DISCLAIMER,
    }


@router.get("/types", summary="Core taxonomy", response_model=Types, responses=problems(422, 429))
def types(request: Request) -> dict[str, Any]:
    reject_unknown(request, frozenset())
    return {
        "composites": {
            name: [
                {"name": field.name, "type": field.type, "nullable": field.nullable}
                for field in fields
            ]
            for name, fields in COMPOSITES.items()
        },
        "atomic": {
            alias: f"{composite}.{field}" for alias, (composite, field) in ATOMIC_ALIASES.items()
        },
    }


@router.get(
    "/universes",
    summary="List the universes",
    response_model=UniverseList,
    responses=problems(404, 410, 422, 429),
)
def universes(request: Request, locale: Locale = None, data_version: DataVersion = None) -> Any:
    reject_unknown(request, LISTING_PARAMS)
    state = app_state(request)
    version = state.store.resolve_version(data_version)
    enabled = state.store.universe_ids(version)
    infos = [
        info for info in state.store.fakeverse(version).universes(locale) if info.id in enabled
    ]
    return {
        "data": [
            {
                "id": info.id,
                "name": info.name,
                "locales": list(info.locales),
                "default_locale": info.default_locale,
            }
            for info in infos
        ],
        "meta": {"data_version": version},
    }


def lenient_generator(
    state: AppState, version: str, universe: str, locale: str | None
) -> UniverseGenerator:
    """A generator for listings: an unsupported language falls back to the default locale."""
    try:
        return state.store.generator(version, universe, locale)
    except LocaleNotSupported:
        return state.store.generator(version, universe, None)


@router.get(
    "/universes/{universe}",
    summary="Detail and capabilities of a universe",
    response_model=UniverseDetail,
    responses=problems(404, 410, 422, 429),
)
def universe_detail(
    request: Request,
    universe: Annotated[str, Path()],
    locale: Locale = None,
    data_version: DataVersion = None,
) -> Any:
    reject_unknown(request, LISTING_PARAMS)
    state = app_state(request)
    version = state.store.resolve_version(data_version)
    generator = lenient_generator(state, version, universe, locale)
    data = generator.index.universe
    meta = data.universe
    levels = {
        level: (
            generator.label(label)
            if data.place_levels is not None
            and (label := getattr(data.place_levels, level)) is not None
            else DEFAULT_PLACE_LEVEL_LABELS[level]
        )
        for level in PLACE_LEVELS
    }
    capabilities = generator.capabilities()
    return {
        "id": meta.id,
        "name": generator.label(meta.name),
        "locales": meta.locales,
        "default_locale": meta.default_locale,
        "sources": {"scope": meta.sources.scope, "translations": meta.sources.translations},
        "maintainers": meta.maintainers,
        "place_levels": levels,
        "capabilities": {
            "core": list(capabilities.core),
            "extensions": [
                {"id": ext.id, "label": generator.label(ext.label), "fields": list(ext.fields)}
                for ext in capabilities.extensions
            ],
        },
        "locale_coverage": {
            locale_id: round(ratio, 4) for locale_id, (ratio, _) in locale_coverage(data).items()
        },
        "meta": {"data_version": version},
    }


def supported_types(generator: UniverseGenerator) -> list[str]:
    capabilities = generator.capabilities()
    return [*capabilities.core, *(ext.id for ext in capabilities.extensions)]


def check_count(count: int, settings: Settings) -> None:
    if count > settings.max_count:
        raise Problem(
            "count-too-large",
            f"Count {count} exceeds the maximum of {settings.max_count}.",
            extra={"max_count": settings.max_count},
        )


def generation_problem(error: FakeverseError, generator: UniverseGenerator) -> Problem:
    extra: dict[str, Any] = {}
    if isinstance(error, TypeNotSupported):
        extra["supported_types"] = supported_types(generator)
    return Problem.from_error(error, extra)


def locale_problem(
    error: LocaleNotSupported, state: AppState, version: str, universe: str
) -> Problem:
    locales = state.store.fakeverse(version).universe(universe).index.universe.universe.locales
    return Problem.from_error(error, {"supported_locales": locales})


def finish(
    request: Request,
    result: GenerationResult,
    output: OutputFormat,
    *,
    explain: bool,
    headers: dict[str, str],
) -> Response:
    state = app_state(request)
    if state.metrics is not None:
        state.metrics.generated.labels(result.meta.universe, result.meta.type).inc(
            len(result.items)
        )
    return generation_response(result, output, explain=explain, headers=headers)


@router.get(
    "/universes/{universe}/generate/{type_id}",
    summary="Generate items of a type",
    response_class=Response,
    responses={**CACHEABLE_GENERATION, **problems(404, 410, 422, 429)},
)
def generate(
    request: Request,
    universe: Annotated[str, Path()],
    type_id: Annotated[str, Path(description="Core or extension type.")],
    count: Annotated[int, Query(ge=1)] = 1,
    seed: Annotated[int | None, Query(ge=0, le=MAX_SEED)] = None,
    locale: Locale = None,
    data_version: DataVersion = None,
    unique: Annotated[
        bool | None,
        Query(
            description="Omitted: avoid duplicates while the pool allows it (meta.duplicates "
            "counts the rest); true: fail with `pool-exhausted` when the pool runs out; "
            "false: allow duplicates."
        ),
    ] = None,
    explain: bool = False,
    format: Annotated[OutputFormat | None, Query()] = None,
    gender: Annotated[Literal["masculine", "feminine", "neutral"] | None, Query()] = None,
    people: Annotated[str | None, Query()] = None,
) -> Response:
    reject_unknown(request, GENERATE_PARAMS)
    state = app_state(request)
    output = negotiate(format, request.headers.get("accept"))
    record(request, universe=universe, type=type_id, count=count, format=output.value)
    check_format(output, explain=explain)
    check_count(count, state.settings)
    version = state.store.resolve_version(data_version)
    try:
        generator = state.store.generator(version, universe, locale)
    except LocaleNotSupported as error:
        raise locale_problem(error, state, version, universe) from error
    try:
        # Validate the type and options first: a 304 must never hide an error.
        resolve_generator(generator.index, type_id, gender=gender, people=people)
    except FakeverseError as error:
        raise generation_problem(error, generator) from error
    headers = {
        "Vary": "Accept",
        "Cache-Control": cache_control(
            seed_given=seed is not None, data_version_given=data_version is not None
        ),
    }
    if seed is not None:
        params = {
            "count": count,
            "seed": seed,
            "locale": generator.locale,
            "unique": unique,
            "explain": explain,
            "format": output.value,
            "gender": gender,
            "people": people,
        }
        tag = etag(f"{universe}/{type_id}", version, params)
        headers["ETag"] = tag
        if matches(request.headers.get("if-none-match"), tag):
            return Response(status_code=304, headers=headers)
    try:
        result = generator.generate(
            type_id, count, seed, unique=unique, explain=explain, gender=gender, people=people
        )
    except FakeverseError as error:
        raise generation_problem(error, generator) from error
    return finish(request, result, output, explain=explain, headers=headers)


class TemplateRequest(BaseModel):
    """Body of a template generation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    template: dict[str, Any]
    count: int = Field(default=1, ge=1)
    seed: int | None = Field(default=None, ge=0, le=MAX_SEED)
    locale: str | None = None
    data_version: str | None = None
    unique: bool | None = None
    explain: bool = False
    format: OutputFormat | None = Field(default=None, strict=False)
    colocate: list[list[str]] = Field(
        default_factory=list,
        description='Groups of instances sharing one locality, e.g. [["person", "organization"]].',
    )


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def load_json(raw: bytes | str) -> Any:
    """Parse standard JSON only: ``NaN`` and ``Infinity`` are refused.

    Raises:
        ValueError: invalid JSON, non-standard constants, or integers too long to convert.
        RecursionError: nesting too deep.
    """
    return json.loads(raw, parse_constant=_reject_constant)


def json_reason(error: ValueError | RecursionError) -> str:
    """Short reason of a JSON parsing failure."""
    if isinstance(error, json.JSONDecodeError):
        return error.msg
    if isinstance(error, RecursionError):
        return "nested too deeply"
    return str(error).split(";")[0]


async def read_body(request: Request) -> bytes:
    """Read the body, stopping as soon as it exceeds the limit (chunked bodies included)."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY:
            raise Problem("payload-too-large", f"The body exceeds {MAX_BODY} bytes.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/universes/{universe}/generate",
    summary="Generate rows from a template",
    response_class=Response,
    responses={**GENERATION, **problems(404, 410, 413, 422, 429)},
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": TemplateRequest.model_json_schema(
                        ref_template="#/components/schemas/{model}"
                    )
                }
            },
        }
    },
)
async def generate_template(request: Request, universe: Annotated[str, Path()]) -> Response:
    reject_unknown(request, frozenset())
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_BODY:
        raise Problem("payload-too-large", f"The body exceeds {MAX_BODY} bytes.")
    raw = await read_body(request)
    try:
        body = TemplateRequest.model_validate(load_json(raw or b"null"))
    except ValidationError as error:
        raise invalid_parameter(
            [
                {
                    "name": ".".join(str(part) for part in e["loc"]) or "body",
                    "location": "body",
                    "message": e["msg"],
                }
                for e in error.errors()
            ]
        ) from error
    except (ValueError, RecursionError) as error:
        raise invalid_parameter(
            [{"name": "body", "location": "body", "message": f"Invalid JSON: {json_reason(error)}"}]
        ) from error

    return await run_template(request, universe, body, cacheable=False)


async def run_template(
    request: Request, universe: str, body: TemplateRequest, *, cacheable: bool
) -> Response:
    """Validate and generate a template request (POST body or GET parameters).

    A cacheable (GET) request gets the cache headers and ETag of a type generation.
    """
    state = app_state(request)
    output = negotiate(body.format, request.headers.get("accept"))
    record(request, universe=universe, type="template", count=body.count, format=output.value)
    check_format(output, explain=body.explain)
    check_count(body.count, state.settings)
    version = state.store.resolve_version(body.data_version)
    try:
        generator = state.store.generator(version, universe, body.locale)
    except LocaleNotSupported as error:
        raise locale_problem(error, state, version, universe) from error
    max_leaves = state.settings.max_template_leaves
    try:
        compiled, groups = compile_with_groups(
            body.template, body.colocate, generator.index, max_leaves=max_leaves
        )
    except FakeverseError as error:
        raise generation_problem(error, generator) from error
    budget = state.settings.max_count * TEMPLATE_BUDGET_FACTOR
    if body.count * len(compiled.instances) > budget:
        raise Problem(
            "count-too-large",
            f"count x instances ({body.count} x {len(compiled.instances)}) exceeds the "
            f"maximum of {budget} generated instances per request.",
            extra={"max_count": state.settings.max_count, "max_instances": budget},
        )
    headers = {"Cache-Control": NO_STORE, "Vary": "Accept"}
    if cacheable:
        headers["Cache-Control"] = cache_control(
            seed_given=body.seed is not None, data_version_given=body.data_version is not None
        )
        if body.seed is not None:
            params = {
                # Key order matters: it is the order of the output.
                "template": json.dumps(body.template, ensure_ascii=False, separators=(",", ":")),
                "colocate": sorted(group.kind for group in groups),
                "count": body.count,
                "seed": body.seed,
                "locale": generator.locale,
                "unique": body.unique,
                "explain": body.explain,
                "format": output.value,
            }
            tag = etag(f"{universe}/template", version, params)
            headers["ETag"] = tag
            if matches(request.headers.get("if-none-match"), tag):
                return Response(status_code=304, headers=headers)
    try:
        # Generation is CPU bound: run it off the event loop.
        result = await run_in_threadpool(
            generator.template,
            body.template,
            body.count,
            body.seed,
            unique=body.unique,
            explain=body.explain,
            max_leaves=max_leaves,
            colocate=body.colocate,
        )
    except FakeverseError as error:
        raise generation_problem(error, generator) from error
    return finish(request, result, output, explain=body.explain, headers=headers)


TEMPLATE_GET_PARAMS: Final[frozenset[str]] = frozenset(
    {
        "template",
        "count",
        "seed",
        "locale",
        "data_version",
        "unique",
        "explain",
        "format",
        "colocate",
    }
)


def parse_groups(text: str | None) -> list[list[str]]:
    """Colocation groups in a query string: ``person,organization;person#2,address``."""
    if not text:
        return []
    return [[member.strip() for member in group.split(",")] for group in text.split(";")]


_BASE64URL = re.compile(r"^[A-Za-z0-9_-]*={0,2}$")


def decode_template(encoded: str) -> Any:
    """Decode a template passed as base64url JSON (padding optional)."""

    def problem(message: str) -> Problem:
        return invalid_parameter([{"name": "template", "location": "query", "message": message}])

    if len(encoded) > MAX_ENCODED_TEMPLATE:
        raise Problem("payload-too-large", f"The template exceeds {MAX_BODY} bytes.")
    if _BASE64URL.match(encoded) is None:
        raise problem("Invalid base64url")
    try:
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except (binascii.Error, ValueError) as error:
        raise problem("Invalid base64url") from error
    if len(raw) > MAX_BODY:
        raise Problem("payload-too-large", f"The template exceeds {MAX_BODY} bytes.")
    try:
        return load_json(raw.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise problem("Invalid UTF-8") from error
    except (ValueError, RecursionError) as error:
        raise problem(f"Invalid JSON: {json_reason(error)}") from error


@router.get(
    "/universes/{universe}/generate",
    summary="Generate rows from a template passed in the URL (cacheable)",
    response_class=Response,
    responses={**CACHEABLE_GENERATION, **problems(404, 410, 413, 422, 429)},
)
async def generate_template_get(
    request: Request,
    universe: Annotated[str, Path()],
    template: Annotated[str, Query(description="The template as base64url-encoded JSON.")],
    count: Annotated[int, Query(ge=1)] = 1,
    seed: Annotated[int | None, Query(ge=0, le=MAX_SEED)] = None,
    locale: Locale = None,
    data_version: DataVersion = None,
    unique: Annotated[
        bool | None,
        Query(
            description="Omitted: avoid duplicates while the pool allows it (meta.duplicates "
            "counts the rest); true: fail with `pool-exhausted` when the pool runs out; "
            "false: allow duplicates."
        ),
    ] = None,
    explain: bool = False,
    format: Annotated[OutputFormat | None, Query()] = None,
    colocate: Annotated[
        str | None,
        Query(description="Groups of instances sharing a locality: `person,organization;...`."),
    ] = None,
) -> Response:
    reject_unknown(request, TEMPLATE_GET_PARAMS)
    try:
        body = TemplateRequest(
            template=decode_template(template),
            count=count,
            seed=seed,
            locale=locale,
            data_version=data_version,
            unique=unique,
            explain=explain,
            format=format,
            colocate=parse_groups(colocate),
        )
    except ValidationError as error:
        raise invalid_parameter(
            [{"name": "template", "location": "query", "message": e["msg"]} for e in error.errors()]
        ) from error
    return await run_template(request, universe, body, cacheable=True)
