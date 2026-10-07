"""Models describing the API responses in the OpenAPI schema (documentation only).

Endpoints build their responses directly; these models give `/docs` and `/openapi.json`
an accurate description of the bodies, formats and RFC 9457 problems.
"""

from __future__ import annotations

from typing import Any, Final

from pydantic import BaseModel, Field

from fakeverse.api.problems import MEDIA_TYPE


class Problem(BaseModel):
    """An RFC 9457 problem (see docs/problems.md); some problems add members."""

    type: str = Field(examples=["/problems/type-not-supported"])
    title: str = Field(examples=["Type not supported"])
    status: int = Field(examples=[404])
    detail: str
    instance: str = Field(examples=["/v1/universes/lotr/generate/starship"])


class GenerationMeta(BaseModel):
    """Metadata of a generation."""

    universe: str
    type: str = Field(description="The generated type, or `template`.")
    count: int
    seed: int = Field(description="Exact seed; also in the `Fakeverse-Seed` header.")
    seed_generated: bool
    locale: str
    locale_fallbacks: int
    data_version: str
    engine_revision: int
    duplicates: int = Field(
        description="Items equal to a previous one: the pool was too small, or unique=false."
    )


class Generation(BaseModel):
    """JSON response of a generation."""

    data: list[Any] = Field(
        description="Items: scalars for atomic types, objects otherwise, explain objects "
        "with `explain=true`."
    )
    meta: GenerationMeta


class Limits(BaseModel):
    max_count: int
    max_template_leaves: int
    max_template_depth: int


class Meta(BaseModel):
    package_version: str
    engine_revision: int
    data_versions: list[str]
    default_data_version: str
    limits: Limits
    disclaimer: str


class TypeField(BaseModel):
    name: str
    type: str
    nullable: bool


class Types(BaseModel):
    composites: dict[str, list[TypeField]]
    atomic: dict[str, str] = Field(description="Atomic type -> projected path.")


class UniverseSummary(BaseModel):
    id: str
    name: str
    locales: list[str]
    default_locale: str


class DataVersionMeta(BaseModel):
    data_version: str


class UniverseList(BaseModel):
    data: list[UniverseSummary]
    meta: DataVersionMeta


class Extension(BaseModel):
    id: str
    label: str
    fields: list[str]


class Capabilities(BaseModel):
    core: list[str]
    extensions: list[Extension]


class Sources(BaseModel):
    scope: str
    translations: dict[str, str]


class UniverseDetail(UniverseSummary):
    sources: Sources
    maintainers: list[str]
    place_levels: dict[str, str]
    capabilities: Capabilities
    locale_coverage: dict[str, float]
    meta: DataVersionMeta


class Health(BaseModel):
    status: str = Field(examples=["ok"])


def problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI responses for problem statuses."""
    return {
        status: {
            "description": DESCRIPTIONS[status],
            "content": {MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}},
        }
        for status in statuses
    }


DESCRIPTIONS: Final[dict[int, str]] = {
    404: "Unknown universe, type or data version (see docs/problems.md).",
    410: "Data version of an older engine revision.",
    413: "Template larger than 64 KB.",
    422: "Invalid parameter, count too large, unsupported locale, invalid template or pool "
    "exhausted.",
    429: "Rate limited; see the `Retry-After` header.",
}

GENERATED: Final[dict[str, Any]] = {
    "description": "Generated items, in the negotiated format (`format` parameter, else "
    "`Accept` header, else JSON). Every format carries the `Fakeverse-*` headers.",
    "content": {
        "application/json": {"schema": {"$ref": "#/components/schemas/Generation"}},
        "application/x-ndjson": {"schema": {"type": "string"}},
        "text/csv": {"schema": {"type": "string"}},
    },
}
NOT_MODIFIED: Final[dict[str, Any]] = {
    "description": "Not modified (`If-None-Match` matched the `ETag`)."
}
CACHEABLE_GENERATION: Final[dict[int | str, dict[str, Any]]] = {200: GENERATED, 304: NOT_MODIFIED}
"""Responses of a generation that can be cached (seeded GET requests)."""
GENERATION: Final[dict[int | str, dict[str, Any]]] = {200: GENERATED}

DOCUMENTED_MODELS: Final[tuple[type[BaseModel], ...]] = (Problem, Generation)
"""Models referenced by ``$ref`` in hand-written responses, added to the components."""
