"""Generated values with their origin, and their raw or explained output."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

type Origin = Literal["canon", "generated"]
type Scalar = str | int | None


@dataclass(frozen=True, slots=True)
class Leaf:
    """A generated scalar value and where it comes from."""

    value: Scalar
    origin: Origin | None
    """None for a null value."""
    locale: str | None
    """Requested locale, or the default locale when the value fell back; None for null."""
    fallback: bool = False
    """Whether the value, or one of its components, fell back to another language."""


NULL = Leaf(None, None, None)

type Node = Leaf | Mapping[str, "Node"]
"""A generated value: a leaf, or an object of nodes in output order."""


def to_output(node: Node, *, explain: bool) -> Any:
    """Convert a node to its JSON output: raw values, or explain objects for each leaf."""
    if isinstance(node, Leaf):
        if not explain:
            return node.value
        return {
            "value": node.value,
            "origin": node.origin,
            "locale": node.locale,
            "fallback": node.fallback,
        }
    return {key: to_output(child, explain=explain) for key, child in node.items()}


def count_fallbacks(node: Node) -> int:
    """Count the leaves of ``node`` that fell back to another language."""
    if isinstance(node, Leaf):
        return int(node.fallback)
    return sum(count_fallbacks(child) for child in node.values())
