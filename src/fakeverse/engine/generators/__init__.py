"""Generators of the core and extension types.

:func:`resolve_generator` checks a type and its options once, and returns a function that
generates one item from a :class:`~fakeverse.engine.generators.common.Draw`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from fakeverse.engine.explain import Leaf, Node
from fakeverse.engine.generators.address import generate_address
from fakeverse.engine.generators.common import Draw
from fakeverse.engine.generators.extensions import generate_extension
from fakeverse.engine.generators.organization import generate_organization
from fakeverse.engine.generators.person import generate_person
from fakeverse.engine.index import LocalityInfo, Pool, UniverseIndex, locality_weight
from fakeverse.errors import InvalidOption, TypeNotSupported
from fakeverse.types import ATOMIC_ALIASES, GENDERS, Gender

type Generator = Callable[[Draw], Node]

PERSON_TYPES: Final[tuple[str, ...]] = (
    "person",
    *(alias for alias, (composite, _field) in ATOMIC_ALIASES.items() if composite == "person"),
)
"""Types that accept the ``gender`` and ``people`` options."""


def supported_types(index: UniverseIndex) -> list[str]:
    """Return the core and extension types supported by a universe."""
    return [*index.capabilities.core, *(ext.id for ext in index.capabilities.extensions)]


def resolve_generator(
    index: UniverseIndex,
    type_id: str,
    *,
    gender: str | None = None,
    people: str | None = None,
) -> Generator:
    """Return the generator of ``type_id`` with the given options.

    Raises:
        TypeNotSupported: if the type is unknown or not supported by the universe.
        InvalidOption: if an option is invalid, not applicable, or impossible to satisfy.
    """
    if not index.capabilities.supports(type_id):
        supported = ", ".join(supported_types(index))
        raise TypeNotSupported(
            f"Universe '{index.id}' does not support type '{type_id}'. Supported: {supported}."
        )
    if type_id in index.extensions:
        _reject_person_options(type_id, gender, people)
        info = index.extensions[type_id]
        return lambda draw: generate_extension(draw, info)

    composite, field = ATOMIC_ALIASES.get(type_id, (type_id, None))
    generator: Generator
    if composite == "person":
        generator = _person_generator(index, type_id, gender, people)
    else:
        _reject_person_options(type_id, gender, people)
        if composite == "address":
            generator = lambda draw: generate_address(draw, index.localities)[0]  # noqa: E731
        else:
            generator = generate_organization
    if field is None:
        return generator
    return lambda draw: _project(generator(draw), field)


type LocatedGenerator = Callable[[Draw, LocalityInfo], Node]


def resolve_located_generator(index: UniverseIndex, type_id: str) -> LocatedGenerator:
    """Generator of a composite instance whose locality is imposed (template colocation)."""
    if type_id == "address":
        return lambda draw, locality: generate_address(draw, Pool([locality], locality_weight))[0]
    if type_id == "person":
        peoples = index.people_pool
        return lambda draw, locality: generate_person(draw, peoples, None, locality)
    return generate_organization


def _project(node: Node, field: str) -> Node:
    if isinstance(node, Leaf):  # pragma: no cover - composites are mappings
        raise TypeError("projection of a scalar")
    return node[field]


def _reject_person_options(type_id: str, gender: str | None, people: str | None) -> None:
    for name, value in (("gender", gender), ("people", people)):
        if value is not None:
            raise InvalidOption(
                f"Option '{name}' only applies to person and its atomic types, not to '{type_id}'."
            )


def _person_generator(
    index: UniverseIndex, type_id: str, gender: str | None, people: str | None
) -> Generator:
    chosen: Gender | None = None
    if gender is not None:
        for candidate in GENDERS:
            if candidate == gender:
                chosen = candidate
        if chosen is None:
            raise InvalidOption(
                f"Invalid gender '{gender}'; expected one of: {', '.join(GENDERS)}."
            )
    if people is not None and all(info.people.id != people for info in index.peoples):
        known = ", ".join(info.people.id for info in index.peoples)
        raise InvalidOption(f"Unknown people '{people}'; expected one of: {known}.")
    pool = index.eligible_peoples(
        gender=chosen, people_id=people, with_family_names=type_id == "last_name"
    )
    if pool is None:
        raise InvalidOption(
            f"No people matches the options (gender={gender}, people={people}) "
            f"for type '{type_id}'."
        )
    return lambda draw: generate_person(draw, pool, chosen)


__all__ = [
    "PERSON_TYPES",
    "Draw",
    "Generator",
    "LocatedGenerator",
    "resolve_generator",
    "resolve_located_generator",
    "supported_types",
]
