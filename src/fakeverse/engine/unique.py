"""Generation of the items of a response, with uniqueness.

Three modes:

- ``best_effort`` (default): no duplicate as long as the pool allows it; once an item is
  still a duplicate after 50 attempts, uniqueness stops being enforced for the rest of the
  response, and the duplicates are counted;
- ``strict``: same items, but an item still duplicated after 50 attempts raises
  ``PoolExhausted``;
- ``off``: duplicates allowed, one draw per item.

Best effort and strict produce the same items as long as the pool is large enough.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from fakeverse.engine.explain import Node, to_output
from fakeverse.errors import PoolExhausted
from fakeverse.rng import canonical_json

MAX_ATTEMPTS: Final[int] = 50

type Uniqueness = Literal["best_effort", "strict", "off"]
type ItemFactory = Callable[[int, int | None], Node]
"""Generates item ``index``; the second argument is the uniqueness attempt, or None."""


def uniqueness(unique: bool | None) -> Uniqueness:
    """Mode of the ``unique`` option: None (default) best effort, True strict, False off."""
    if unique is None:
        return "best_effort"
    return "strict" if unique else "off"


@dataclass(frozen=True, slots=True)
class Items:
    """Generated items and the number of them that repeat a previous item."""

    nodes: list[Node]
    duplicates: int


def generate_items(count: int, make: ItemFactory, mode: Uniqueness) -> Items:
    """Generate ``count`` items.

    With ``off``, item ``i`` is ``make(i, None)``. Otherwise, item ``i`` is the first of
    ``make(i, 0)``, ``make(i, 1)``... whose raw output differs from every previous item. Each
    item only depends on the previous ones, so prefixes stay stable.

    Raises:
        PoolExhausted: in ``strict`` mode, when an item is still a duplicate after 50
            attempts.
    """
    if mode == "off":
        nodes = [make(index, None) for index in range(count)]
        seen: dict[bytes, None] = {}
        duplicates = 0
        for node in nodes:
            key = canonical_json(to_output(node, explain=False))
            duplicates += key in seen
            seen[key] = None
        return Items(nodes, duplicates)
    seen = {}
    nodes = []
    duplicates = 0
    exhausted = False
    for index in range(count):
        if exhausted:
            node = make(index, 0)
            key = canonical_json(to_output(node, explain=False))
            duplicates += key in seen
            seen[key] = None
            nodes.append(node)
            continue
        for attempt in range(MAX_ATTEMPTS):
            node = make(index, attempt)
            key = canonical_json(to_output(node, explain=False))
            if key not in seen:
                seen[key] = None
                nodes.append(node)
                break
        else:
            if mode == "strict":
                raise PoolExhausted(
                    f"Could not generate {count} unique items: the pool ran out after {len(nodes)} "
                    f"({MAX_ATTEMPTS} attempts failed for the next one).",
                    unique_count=len(nodes),
                )
            # Best effort: the pool is exhausted; keep the first attempt, stop enforcing.
            exhausted = True
            nodes.append(make(index, 0))
            duplicates += 1
    return Items(nodes, duplicates)
