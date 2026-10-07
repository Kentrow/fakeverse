"""Coherence invariants of generated data.

Used by ``fakeverse check-coherence`` and by the property tests. Checks work on the raw
output, as a user sees it, and match values back to the universe data by name.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from fakeverse.engine.index import LocalityInfo, PeopleInfo, UniverseIndex
from fakeverse.fakeverse import Fakeverse, UniverseGenerator
from fakeverse.locale import LocalizedValue, resolve
from fakeverse.patterns import FieldToken
from fakeverse.patterns.renderer import slugify
from fakeverse.types import ATOMIC_ALIASES, COMPOSITES


@dataclass(frozen=True, slots=True)
class Violation:
    """A broken invariant."""

    universe: str
    locale: str
    type: str
    item: int
    message: str

    def format(self) -> str:
        return f"{self.universe} [{self.locale}] {self.type} #{self.item}: {self.message}"


class _Checker:
    def __init__(self, generator: UniverseGenerator) -> None:
        self.index: UniverseIndex = generator.index
        self.locale = generator.locale

    def name(self, value: LocalizedValue | None) -> str | None:
        if value is None:
            return None
        return resolve(value, self.locale, self.index.default_locale).value

    def localities(self, address: Mapping[str, Any]) -> list[LocalityInfo]:
        """Localities matching an address by the names of the locality and its ancestors."""
        return [
            info
            for info in self.index.locality_infos.values()
            if self.name(info.place.name) == address["locality"]
            and self.name(info.subdivision.name if info.subdivision else None)
            == address["subdivision"]
            and self.name(info.area.name) == address["area"]
        ]

    def check(self, type_id: str, value: Any) -> Iterator[str]:
        if type_id in self.index.extensions:
            yield from self.check_extension(value)
        elif type_id == "address":
            yield from self.check_address(value)
        elif type_id == "person":
            yield from self.check_person(value)
        elif type_id == "organization":
            yield from self.check_organization(value)
        else:
            composite, field = ATOMIC_ALIASES[type_id]
            nullable = next(f.nullable for f in COMPOSITES[composite] if f.name == field)
            if type_id == "last_name":
                nullable = False
            yield from _non_empty(type_id, value, nullable=nullable)

    def check_address(self, address: Mapping[str, Any]) -> Iterator[str]:
        yield from _non_empty_fields("address", address)
        if not self.localities(address):
            yield (
                f"invariant 1: locality '{address['locality']}' does not have subdivision "
                f"'{address['subdivision']}' and area '{address['area']}' as ancestors"
            )

    def check_person(self, person: Mapping[str, Any]) -> Iterator[str]:
        yield from _non_empty_fields("person", person)
        yield from self.check_address(person["address"])
        peoples = [
            info for info in self.index.peoples if self.name(info.people.name) == person["people"]
        ]
        if not peoples:
            yield f"unknown people '{person['people']}'"
            return
        located = [
            info
            for info in peoples
            if any(
                candidate.place.id == locality.place.id
                for locality in self.localities(person["address"])
                for candidate in info.localities.items
            )
        ]
        if not located:
            yield (
                f"invariant 2: address in '{person['address']['locality']}' is outside the "
                f"homelands of '{person['people']}'"
            )
        if not any(self.has_first_name(info, person) for info in peoples):
            yield (
                f"invariant 3: first name '{person['first_name']}' (gender {person['gender']}) "
                f"does not belong to '{person['people']}'"
            )
        if not any(self.has_last_name(info, person["last_name"]) for info in peoples):
            yield f"invariant 4: last name {person['last_name']!r} does not match the people"
        yield from self.check_email(person)

    def has_first_name(self, info: PeopleInfo, person: Mapping[str, Any]) -> bool:
        return any(
            self.name(item.value) == person["first_name"]
            and (item.gender is None or item.gender == person["gender"])
            for item in info.people.first_names
        )

    def has_last_name(self, info: PeopleInfo, last_name: str | None) -> bool:
        families = info.people.family_names
        if families is None:
            return last_name is None
        return any(self.name(item.value) == last_name for item in families)

    def check_email(self, person: Mapping[str, Any]) -> Iterator[str]:
        email = person["email"]
        if email is None or self.index.email is None:
            return
        pattern, _fallback = self.index.email.resolve(self.locale, self.index.default_locale)
        uses_slug = any(
            isinstance(s, FieldToken) and s.name == "first_name" and s.filters[:1] == ("slug",)
            for s in pattern.segments
        )
        if uses_slug and slugify(person["first_name"]) not in email:
            yield f"invariant 5: email '{email}' does not contain the slug of the first name"

    def check_organization(self, org: Mapping[str, Any]) -> Iterator[str]:
        yield from _non_empty_fields("organization", org)
        yield from self.check_address(org["address"])
        if self.index.organizations is None:
            return
        candidates = [
            info
            for info in self.index.organizations.items
            if self.name(info.organization.name) == org["name"]
            and self.name(info.organization.kind) == org["kind"]
        ]
        maybe_generated = org["kind"] is None and self.index.organization_name is not None
        if candidates and not maybe_generated:
            localities = self.localities(org["address"])
            if not any(
                candidate.place.id == locality.place.id
                for info in candidates
                for candidate in info.localities.items
                for locality in localities
            ):
                yield f"invariant 6: organization '{org['name']}' is outside its places"

    def check_extension(self, item: Mapping[str, Any]) -> Iterator[str]:
        for key, value in item.items():
            yield from _non_empty(key, value, nullable=False)


def _non_empty(name: str, value: Any, *, nullable: bool) -> Iterator[str]:
    if value is None:
        if not nullable:
            yield f"invariant 7: '{name}' is null"
    elif value == "":
        yield f"invariant 7: '{name}' is empty"


def _non_empty_fields(composite: str, value: Mapping[str, Any]) -> Iterator[str]:
    for field in COMPOSITES[composite]:
        if field.type in COMPOSITES:
            continue
        yield from _non_empty(field.name, value[field.name], nullable=field.nullable)


def check_items(generator: UniverseGenerator, type_id: str, items: list[Any]) -> list[str]:
    """Return the invariant violations of generated raw items of one type."""
    checker = _Checker(generator)
    return [
        f"#{position}: {message}"
        for position, item in enumerate(items)
        for message in checker.check(type_id, item)
    ]


def check_universe(
    fakeverse: Fakeverse, universe_id: str, *, count: int, seed: int
) -> list[Violation]:
    """Generate ``count`` items of every supported type in every locale and check them."""
    violations: list[Violation] = []
    meta = fakeverse.universe(universe_id).index.universe.universe
    for locale in meta.locales:
        generator = fakeverse.universe(universe_id, locale)
        capabilities = generator.capabilities()
        for type_id in [*capabilities.core, *(ext.id for ext in capabilities.extensions)]:
            items = generator.generate(type_id, count, seed).items
            if generator.generate(type_id, count, seed).items != items:
                violations.append(
                    Violation(universe_id, locale, type_id, 0, "invariant 8: not deterministic")
                )
            checker = _Checker(generator)
            violations.extend(
                Violation(universe_id, locale, type_id, position, message)
                for position, item in enumerate(items)
                for message in checker.check(type_id, item)
            )
    return violations
