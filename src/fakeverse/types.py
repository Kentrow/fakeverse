"""Core taxonomy of Fakeverse.

The taxonomy is defined once by the project. Universes do not declare which core types
they support: support is derived from their data (see :mod:`fakeverse.capabilities`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

type PlaceLevel = Literal["area", "subdivision", "locality"]
type Gender = Literal["masculine", "feminine", "neutral"]

PLACE_LEVELS: Final[tuple[PlaceLevel, ...]] = ("area", "subdivision", "locality")
GENDERS: Final[tuple[Gender, ...]] = ("masculine", "feminine", "neutral")
"""Genders in their fixed draw order."""


@dataclass(frozen=True, slots=True)
class Field:
    """A field of a core composite type."""

    name: str
    type: str
    """``string``, ``gender`` or the name of a composite type."""
    nullable: bool


COMPOSITES: Final[dict[str, tuple[Field, ...]]] = {
    "address": (
        Field("street_address", "string", nullable=False),
        Field("postal_code", "string", nullable=True),
        Field("locality", "string", nullable=False),
        Field("subdivision", "string", nullable=True),
        Field("area", "string", nullable=False),
        Field("formatted", "string", nullable=False),
    ),
    "person": (
        Field("first_name", "string", nullable=False),
        Field("last_name", "string", nullable=True),
        Field("full_name", "string", nullable=False),
        Field("gender", "gender", nullable=True),
        Field("people", "string", nullable=False),
        Field("address", "address", nullable=False),
        Field("email", "string", nullable=True),
        Field("username", "string", nullable=True),
        Field("phone", "string", nullable=True),
    ),
    "organization": (
        Field("name", "string", nullable=False),
        Field("kind", "string", nullable=True),
        Field("address", "address", nullable=False),
        Field("phone", "string", nullable=True),
    ),
}
"""Core composite types and their fields, in output order."""

ATOMIC_ALIASES: Final[dict[str, tuple[str, str]]] = {
    "first_name": ("person", "first_name"),
    "last_name": ("person", "last_name"),
    "full_name": ("person", "full_name"),
    "email": ("person", "email"),
    "username": ("person", "username"),
    "phone": ("person", "phone"),
    "street_address": ("address", "street_address"),
    "postal_code": ("address", "postal_code"),
    "locality": ("address", "locality"),
    "subdivision": ("address", "subdivision"),
    "area": ("address", "area"),
    "organization_name": ("organization", "name"),
}
"""Atomic types, each defined as the projection ``(composite, field)``."""

CORE_TYPES: Final[tuple[str, ...]] = (*COMPOSITES, *ATOMIC_ALIASES)
"""All core types: composites first, then atomic aliases."""

RESERVED_TYPE_IDS: Final[frozenset[str]] = frozenset({*CORE_TYPES, "template"})
"""Identifiers that an extension may not use."""

PLACE_CONTEXT: Final[tuple[str, ...]] = ("locality", "subdivision", "area")
PERSON_CONTEXT: Final[tuple[str, ...]] = ("first_name", "family_name", "people", *PLACE_CONTEXT)

PATTERN_CONTEXT: Final[dict[str, tuple[str, ...]]] = {
    "street_address": PLACE_CONTEXT,
    "postal_code": PLACE_CONTEXT,
    "address_format": (*PLACE_CONTEXT, "street_address", "postal_code"),
    "phone": PLACE_CONTEXT,
    "email": PERSON_CONTEXT,
    "username": PERSON_CONTEXT,
    "organization_name": PLACE_CONTEXT,
}
"""Patterns recognized by the core and the context fields each one may use.

``phone`` is shared by persons and organizations, so it only sees place fields.
"""

NAME_FORMAT_CONTEXT: Final[tuple[str, ...]] = PERSON_CONTEXT
"""Context fields of a people's ``name_format``."""

OVERRIDABLE_PATTERNS: Final[tuple[str, ...]] = (
    "street_address",
    "postal_code",
    "address_format",
    "phone",
)
"""Patterns that a place may override for itself and its descendants."""

DEFAULT_ADDRESS_FORMAT: Final[str] = "{street_address}, {locality}, {area}"

DEFAULT_PLACE_LEVEL_LABELS: Final[dict[PlaceLevel, str]] = {
    "area": "Area",
    "subdivision": "Subdivision",
    "locality": "Locality",
}
