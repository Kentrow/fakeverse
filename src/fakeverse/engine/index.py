"""Compiled form of a universe, built once at load time.

Every list follows the order of the universe file, cumulative weights are computed here, and
patterns are parsed here. Generation then runs without I/O or parsing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from itertools import accumulate

from fakeverse.capabilities import Capabilities, compute_capabilities
from fakeverse.hierarchy import PlaceTree
from fakeverse.locale import LocalizedValue, resolve
from fakeverse.model import (
    Extension,
    ExtensionItem,
    FamilyNameItem,
    FirstNameItem,
    Organization,
    People,
    Place,
    UniverseFile,
    VocabItem,
)
from fakeverse.patterns import Pattern, parse_pattern
from fakeverse.rng import Rng
from fakeverse.types import DEFAULT_ADDRESS_FORMAT, GENDERS, Gender, PlaceLevel


class Pool[T]:
    """A non-empty list of items drawn with integer weights."""

    __slots__ = ("cumulative", "items")

    def __init__(self, items: Sequence[T], weight: Callable[[T], int]) -> None:
        if not items:
            raise ValueError("a pool needs at least one item")
        self.items: tuple[T, ...] = tuple(items)
        self.cumulative: tuple[int, ...] = tuple(accumulate(weight(item) for item in items))

    def draw(self, rng: Rng) -> T:
        """Draw one item."""
        return self.items[rng.weighted_index(self.cumulative)]


@dataclass(frozen=True, slots=True)
class LocalizedPattern:
    """A localized pattern with each of its variants parsed."""

    raw: LocalizedValue
    variants: dict[str | None, Pattern]
    """Parsed variants by locale key; the key None holds a plain string pattern."""

    @classmethod
    def parse(cls, raw: LocalizedValue) -> LocalizedPattern:
        if isinstance(raw, str):
            return cls(raw, {None: parse_pattern(raw)})
        return cls(raw, {locale: parse_pattern(source) for locale, source in raw.items()})

    def resolve(self, locale: str, default_locale: str) -> tuple[Pattern, bool]:
        """Return the variant for ``locale`` and whether it is a counted fallback."""
        resolved = resolve(self.raw, locale, default_locale)
        return self.variants[resolved.locale], resolved.fallback


def _optional_pattern(raw: LocalizedValue | None) -> LocalizedPattern | None:
    return None if raw is None else LocalizedPattern.parse(raw)


@dataclass(frozen=True, slots=True)
class LocalityInfo:
    """A locality with its ancestors and the patterns that apply to it."""

    place: Place
    subdivision: Place | None
    area: Place
    street_address: LocalizedPattern | None
    postal_code: LocalizedPattern | None
    address_format: LocalizedPattern
    phone: LocalizedPattern | None


@dataclass(frozen=True, slots=True)
class PeopleInfo:
    """A people with its name pools and the localities of its homelands."""

    people: People
    name_format: LocalizedPattern
    genders: Pool[tuple[Gender, int]] | None
    """Genders present among the first names, in fixed order, weighted by the sum of the
    weights of their first names; None when no first name has a gender."""
    first_names: dict[Gender | None, Pool[FirstNameItem]]
    """First names usable with each gender (that gender or no gender); key None: all names."""
    family_names: Pool[FamilyNameItem] | None
    localities: Pool[LocalityInfo]

    def accepts_gender(self, gender: Gender) -> bool:
        """Whether the people has a first name of ``gender`` or without gender."""
        return gender in self.first_names


@dataclass(frozen=True, slots=True)
class OrganizationInfo:
    """A canonical organization with the localities where it can be located."""

    organization: Organization
    localities: Pool[LocalityInfo]


@dataclass(frozen=True, slots=True)
class ExtensionInfo:
    """An extension type with its compiled data."""

    id: str
    extension: Extension
    items: Pool[ExtensionItem] | None
    patterns: dict[str, LocalizedPattern]
    """Parsed patterns of the ``fields`` form, by field."""


@dataclass(slots=True)
class UniverseIndex:
    """Everything the engine needs to generate data for one universe."""

    universe: UniverseFile
    tree: PlaceTree
    capabilities: Capabilities
    localities: Pool[LocalityInfo]
    locality_infos: dict[str, LocalityInfo]
    places_by_level: dict[PlaceLevel, Pool[Place]]
    peoples: tuple[PeopleInfo, ...]
    people_pool: Pool[PeopleInfo]
    organizations: Pool[OrganizationInfo] | None
    vocab: dict[str, Pool[VocabItem]]
    email: LocalizedPattern | None
    username: LocalizedPattern | None
    organization_name: LocalizedPattern | None
    extensions: dict[str, ExtensionInfo]
    _people_pools: dict[tuple[Gender | None, str | None, bool], Pool[PeopleInfo] | None] = field(
        default_factory=dict
    )

    @property
    def id(self) -> str:
        return self.universe.universe.id

    @property
    def default_locale(self) -> str:
        return self.universe.universe.default_locale

    def eligible_peoples(
        self, *, gender: Gender | None, people_id: str | None, with_family_names: bool
    ) -> Pool[PeopleInfo] | None:
        """Return the pool of peoples compatible with the options, or None if empty."""
        key = (gender, people_id, with_family_names)
        if key not in self._people_pools:
            eligible = [
                info
                for info in self.peoples
                if (people_id is None or info.people.id == people_id)
                and (gender is None or info.accepts_gender(gender))
                and (not with_family_names or info.family_names is not None)
            ]
            self._people_pools[key] = Pool(eligible, people_weight) if eligible else None
        return self._people_pools[key]


def hosts(pool: Pool[LocalityInfo], locality: LocalityInfo) -> bool:
    """Whether ``locality`` is one of the localities of ``pool`` (identity, not equality)."""
    return any(item is locality for item in pool.items)


def people_weight(info: PeopleInfo) -> int:
    return info.people.weight


def _place_weight(place: Place) -> int:
    return place.weight


def locality_weight(info: LocalityInfo) -> int:
    return info.place.weight


def _item_weight(item: FirstNameItem | FamilyNameItem | VocabItem) -> int:
    return item.weight


def build_index(universe: UniverseFile) -> UniverseIndex:
    """Compile a valid universe."""
    tree = PlaceTree(universe.places)
    patterns = universe.patterns
    locality_infos: dict[str, LocalityInfo] = {}
    for place in tree.localities():
        area = tree.ancestor_at(place.id, "area")
        if area is None:  # pragma: no cover - excluded by validation
            raise ValueError(f"locality {place.id!r} has no area")

        def pattern(name: str, place_id: str = place.id) -> LocalizedPattern | None:
            return _optional_pattern(tree.resolve_pattern(place_id, name, patterns))

        locality_infos[place.id] = LocalityInfo(
            place=place,
            subdivision=tree.ancestor_at(place.id, "subdivision"),
            area=area,
            street_address=pattern("street_address"),
            postal_code=pattern("postal_code"),
            address_format=pattern("address_format")
            or LocalizedPattern.parse(DEFAULT_ADDRESS_FORMAT),
            phone=pattern("phone"),
        )

    def locality_pool(place_ids: Sequence[str]) -> Pool[LocalityInfo]:
        wanted = {
            locality.id: True
            for place_id in place_ids
            for locality in tree.localities_under(place_id)
        }
        return Pool(
            [info for info in locality_infos.values() if info.place.id in wanted], locality_weight
        )

    peoples = tuple(_people_info(people, locality_pool) for people in universe.peoples)
    organizations = [
        OrganizationInfo(
            organization=org,
            localities=locality_pool(org.places or [p.id for p in tree.localities()]),
        )
        for org in universe.organizations
    ]
    places_by_level: dict[PlaceLevel, Pool[Place]] = {}
    for level in ("area", "subdivision", "locality"):
        of_level = [place for place in universe.places if place.level == level]
        if of_level:
            places_by_level[level] = Pool(of_level, _place_weight)
    return UniverseIndex(
        universe=universe,
        tree=tree,
        capabilities=compute_capabilities(universe),
        localities=Pool(list(locality_infos.values()), locality_weight),
        locality_infos=locality_infos,
        places_by_level=places_by_level,
        peoples=peoples,
        people_pool=Pool(peoples, people_weight),
        organizations=Pool(organizations, organization_weight) if organizations else None,
        vocab={name: Pool(items, _item_weight) for name, items in universe.vocab.items()},
        email=_optional_pattern(patterns.email),
        username=_optional_pattern(patterns.username),
        organization_name=_optional_pattern(patterns.organization_name),
        extensions={
            ext_id: _extension_info(ext_id, ext) for ext_id, ext in universe.extensions.items()
        },
    )


def _extension_item_weight(item: ExtensionItem) -> int:
    return item.weight


def organization_weight(info: OrganizationInfo) -> int:
    return info.organization.weight


def _gender_weight(entry: tuple[Gender, int]) -> int:
    return entry[1]


def _people_info(
    people: People, locality_pool: Callable[[Sequence[str]], Pool[LocalityInfo]]
) -> PeopleInfo:
    names = people.first_names
    gender_weights = tuple(
        (gender, sum(item.weight for item in names if item.gender == gender))
        for gender in GENDERS
        if any(item.gender == gender for item in names)
    )
    first_names: dict[Gender | None, Pool[FirstNameItem]] = {None: Pool(names, _item_weight)}
    for gender in GENDERS:
        usable = [item for item in names if item.gender in (gender, None)]
        if usable:
            first_names[gender] = Pool(usable, _item_weight)
    if people.name_format is not None:
        name_format = people.name_format
    else:
        name_format = "{first_name} {family_name}" if people.family_names else "{first_name}"
    return PeopleInfo(
        people=people,
        name_format=LocalizedPattern.parse(name_format),
        genders=Pool(gender_weights, _gender_weight) if gender_weights else None,
        first_names=first_names,
        family_names=Pool(people.family_names, _item_weight) if people.family_names else None,
        localities=locality_pool(people.homelands),
    )


def _extension_info(ext_id: str, ext: Extension) -> ExtensionInfo:
    items = Pool(ext.items, _extension_item_weight) if ext.items else None
    patterns = {
        key: LocalizedPattern.parse(spec.pattern)
        for key, spec in (ext.fields or {}).items()
        if spec.pattern is not None
    }
    return ExtensionInfo(id=ext_id, extension=ext, items=items, patterns=patterns)
