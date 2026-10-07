"""Navigation in the place hierarchy of a universe.

Every listing follows the order of the universe file, so that anything derived from it can
feed a deterministic draw.
"""

from __future__ import annotations

from collections.abc import Sequence

from fakeverse.locale import LocalizedValue
from fakeverse.model import Patterns, Place
from fakeverse.types import PlaceLevel


class PlaceTree:
    """Index of the places of a universe.

    The tree tolerates invalid data (unknown parents, cycles) so that it can be used while
    validating; on a valid universe it is exact.
    """

    def __init__(self, places: Sequence[Place]) -> None:
        self.places: tuple[Place, ...] = tuple(places)
        self.by_id: dict[str, Place] = {}
        for place in self.places:
            self.by_id.setdefault(place.id, place)

    def chain(self, place_id: str) -> list[Place]:
        """Return the place followed by its ancestors, nearest first."""
        chain: list[Place] = []
        seen: list[str] = []
        current = self.by_id.get(place_id)
        while current is not None and current.id not in seen:
            chain.append(current)
            seen.append(current.id)
            current = self.by_id.get(current.parent) if current.parent is not None else None
        return chain

    def ancestor_at(self, place_id: str, level: PlaceLevel) -> Place | None:
        """Return the nearest place of ``level`` in the chain of ``place_id``."""
        for place in self.chain(place_id):
            if place.level == level:
                return place
        return None

    def localities_under(self, place_id: str) -> list[Place]:
        """Return the localities that are ``place_id`` or one of its descendants."""
        return [
            place
            for place in self.places
            if place.level == "locality"
            and any(link.id == place_id for link in self.chain(place.id))
        ]

    def localities(self) -> list[Place]:
        """Return every locality, in file order."""
        return [place for place in self.places if place.level == "locality"]

    def resolve_pattern(
        self, place_id: str, name: str, universe_patterns: Patterns
    ) -> LocalizedValue | None:
        """Return the pattern ``name`` that applies to a place.

        The override of the nearest place of the chain (the place itself included) wins over
        the pattern of the universe.
        """
        for place in self.chain(place_id):
            if place.patterns is not None:
                override: LocalizedValue | None = getattr(place.patterns, name)
                if override is not None:
                    return override
        universe_pattern: LocalizedValue | None = getattr(universe_patterns, name)
        return universe_pattern
