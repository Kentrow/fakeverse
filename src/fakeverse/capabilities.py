"""Types supported by a universe, derived from its data."""

from __future__ import annotations

from dataclasses import dataclass

from fakeverse.hierarchy import PlaceTree
from fakeverse.locale import LocalizedValue
from fakeverse.model import UniverseFile
from fakeverse.types import CORE_TYPES


@dataclass(frozen=True, slots=True)
class ExtensionCapability:
    """An extension type of a universe."""

    id: str
    label: LocalizedValue
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Capabilities:
    """Types supported by a universe."""

    core: tuple[str, ...]
    """Supported core types, in the order of :data:`fakeverse.types.CORE_TYPES`."""
    unsupported: dict[str, str]
    """Unsupported core types and the reason, in the same order."""
    extensions: tuple[ExtensionCapability, ...]

    def supports(self, type_id: str) -> bool:
        """Return whether ``type_id`` (core or extension) is supported."""
        return type_id in self.core or any(ext.id == type_id for ext in self.extensions)


def compute_capabilities(universe: UniverseFile) -> Capabilities:
    """Compute the types supported by a valid universe."""
    tree = PlaceTree(universe.places)
    patterns = universe.patterns
    localities = tree.localities()

    def resolvable(name: str, among: list[str]) -> bool:
        return any(tree.resolve_pattern(place_id, name, patterns) is not None for place_id in among)

    locality_ids = [place.id for place in localities]
    person_localities = [
        place.id
        for people in universe.peoples
        for homeland in people.homelands
        for place in tree.localities_under(homeland)
    ]

    reasons: dict[str, str | None] = {}
    if not localities:
        reasons["address"] = "no locality"
    elif not all(
        tree.resolve_pattern(place_id, "street_address", patterns) is not None
        for place_id in locality_ids
    ):
        reasons["address"] = "some localities resolve no 'street_address' pattern"
    else:
        reasons["address"] = None
    address = reasons["address"]

    reasons["person"] = address if address else (None if universe.peoples else "no people")
    if reasons["person"] is None and not person_localities:
        reasons["person"] = "no locality in the homelands of the peoples"
    person = reasons["person"]

    if address:
        reasons["organization"] = address
    elif not universe.organizations and patterns.organization_name is None:
        reasons["organization"] = "no organization and no 'organization_name' pattern"
    else:
        reasons["organization"] = None

    reasons["first_name"] = person
    reasons["full_name"] = person
    reasons["last_name"] = person or (
        None
        if any(people.family_names for people in universe.peoples)
        else "no people with family names"
    )
    reasons["email"] = person or (None if patterns.email else "no 'email' pattern")
    reasons["username"] = person or (None if patterns.username else "no 'username' pattern")
    reasons["phone"] = person or (
        None if resolvable("phone", person_localities) else "no 'phone' pattern"
    )
    reasons["street_address"] = address
    reasons["postal_code"] = address or (
        None if resolvable("postal_code", locality_ids) else "no 'postal_code' pattern"
    )
    reasons["locality"] = address
    reasons["subdivision"] = address or (
        None
        if any(tree.ancestor_at(place_id, "subdivision") for place_id in locality_ids)
        else "no locality belongs to a subdivision"
    )
    reasons["area"] = address
    reasons["organization_name"] = reasons["organization"]

    extensions = tuple(
        ExtensionCapability(
            id=ext_id,
            label=ext.label,
            fields=(("name", *ext.items[0].fields) if ext.items else tuple(ext.fields or ())),
        )
        for ext_id, ext in universe.extensions.items()
    )
    return Capabilities(
        core=tuple(t for t in CORE_TYPES if reasons[t] is None),
        unsupported={t: reason for t in CORE_TYPES if (reason := reasons[t]) is not None},
        extensions=extensions,
    )
