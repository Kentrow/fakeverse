"""Templates: rows combining several coherent types.

A template is a JSON object whose leaves are paths ``type[#n].field[.sub-field...]``. Leaves
that reference the same instance ``(type, n)`` share one generated value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from fakeverse.engine.explain import Leaf, Node
from fakeverse.engine.index import UniverseIndex
from fakeverse.errors import InvalidTemplate
from fakeverse.types import ATOMIC_ALIASES, COMPOSITES

MAX_DEPTH: Final[int] = 4
DEFAULT_MAX_LEAVES: Final[int] = 50

_PATH = re.compile(
    r"^(?P<type>[a-z0-9]+(?:[-_][a-z0-9]+)*)(?:#(?P<n>[1-9]))?(?:\.(?P<fields>.+))?$"
)

type Instance = tuple[str, int]


@dataclass(frozen=True, slots=True)
class TemplateLeaf:
    """A resolved leaf: an instance and the field path inside it."""

    instance: Instance
    fields: tuple[str, ...]


type Structure = Mapping[str, "TemplateLeaf | Structure"]


@dataclass(frozen=True, slots=True)
class CompiledTemplate:
    """A validated template."""

    structure: Structure
    instances: tuple[Instance, ...]
    """Instances in order of first appearance."""

    def instance_kind(self, instance: Instance) -> str:
        """The ``kind`` of an instance in the seed derivation: ``template:<type>#<n>``."""
        type_id, number = instance
        return f"template:{type_id}#{number}"


def _pointer(keys: tuple[str, ...]) -> str:
    return "".join("/" + key.replace("~", "~0").replace("/", "~1") for key in keys)


@dataclass(slots=True)
class _Compiler:
    index: UniverseIndex
    max_leaves: int
    errors: list[dict[str, object]] = field(default_factory=list)
    instances: dict[Instance, None] = field(default_factory=dict)
    leaves: int = 0

    def error(self, keys: tuple[str, ...], leaf: object, reason: str) -> None:
        self.errors.append({"path": _pointer(keys), "leaf": leaf, "reason": reason})

    def walk(self, template: Mapping[str, object], keys: tuple[str, ...], depth: int) -> Structure:
        structure: dict[str, TemplateLeaf | Structure] = {}
        for key, value in template.items():
            here = (*keys, key)
            if isinstance(value, dict):
                if depth >= MAX_DEPTH:
                    self.error(here, None, f"Templates are limited to {MAX_DEPTH} levels")
                elif not value:
                    self.error(here, None, "Empty object")
                else:
                    structure[key] = self.walk(value, here, depth + 1)
            elif isinstance(value, str):
                self.leaves += 1
                leaf = self.leaf(value, here)
                if leaf is not None:
                    structure[key] = leaf
            else:
                self.error(here, value, "A leaf must be a path string or an object")
        return structure

    def leaf(self, path: str, keys: tuple[str, ...]) -> TemplateLeaf | None:
        resolved = self.resolve(path)
        if isinstance(resolved, str):
            self.error(keys, path, resolved)
            return None
        self.instances.setdefault(resolved.instance, None)
        return resolved

    def resolve(self, path: str) -> TemplateLeaf | str:
        """Resolve a path, or return the reason why it is invalid."""
        match = _PATH.match(path)
        if match is None:
            return "Invalid path; expected type[#n].field[.sub-field]"
        type_id, number = match["type"], int(match["n"] or 1)
        fields = tuple(match["fields"].split(".")) if match["fields"] else ()
        # An alias is its projection: it follows the support of its composite.
        checked = ATOMIC_ALIASES[type_id][0] if type_id in ATOMIC_ALIASES else type_id
        if not self.index.capabilities.supports(checked):
            return f"Type '{type_id}' is not supported by this universe"
        if type_id in ATOMIC_ALIASES:
            if fields:
                return f"Atomic type '{type_id}' has no field"
            composite, projected = ATOMIC_ALIASES[type_id]
            return TemplateLeaf((composite, number), (projected,))
        if not fields:
            return f"A field of '{type_id}' is required"
        reason = self.check_fields(type_id, fields)
        return reason if reason is not None else TemplateLeaf((type_id, number), fields)

    def check_fields(self, type_id: str, fields: tuple[str, ...]) -> str | None:
        if type_id not in COMPOSITES:
            extension = next(e for e in self.index.capabilities.extensions if e.id == type_id)
            if len(fields) != 1 or fields[0] not in extension.fields:
                return f"Unknown field; '{type_id}' has: {', '.join(extension.fields)}"
            return None
        current = type_id
        for position, name in enumerate(fields):
            known = {f.name: f for f in COMPOSITES[current]}
            if name not in known:
                return f"Unknown field '{name}'; '{current}' has: {', '.join(known)}"
            if known[name].type in COMPOSITES:
                current = known[name].type
            elif position != len(fields) - 1:
                return f"Field '{name}' has no sub-field"
        return None


def compile_template(
    template: object, index: UniverseIndex, *, max_leaves: int = DEFAULT_MAX_LEAVES
) -> CompiledTemplate:
    """Validate a template and resolve its paths, before any generation.

    Raises:
        InvalidTemplate: with every faulty leaf at once.
    """
    if not isinstance(template, dict) or not template:
        raise InvalidTemplate(
            "A template must be a non-empty JSON object.",
            [{"path": "", "leaf": None, "reason": "Expected a non-empty object"}],
        )
    compiler = _Compiler(index, max_leaves)
    structure = compiler.walk(template, (), 1)
    if compiler.leaves > max_leaves:
        compiler.error((), None, f"{compiler.leaves} leaves; the maximum is {max_leaves}")
    if compiler.errors:
        raise InvalidTemplate(
            f"Invalid template: {len(compiler.errors)} error(s).", compiler.errors
        )
    return CompiledTemplate(structure, tuple(compiler.instances))


def render_row(structure: Structure, instances: Mapping[Instance, Node]) -> Node:
    """Build one row of output from the generated instances."""
    row: dict[str, Node] = {}
    for key, entry in structure.items():
        if isinstance(entry, TemplateLeaf):
            node = instances[entry.instance]
            for name in entry.fields:
                if isinstance(node, Leaf):  # pragma: no cover - paths are validated
                    raise TypeError("path goes through a scalar")
                node = node[name]
            row[key] = node
        else:
            row[key] = render_row(entry, instances)
    return row
