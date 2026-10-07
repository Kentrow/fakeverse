"""Colocation of template instances: instances that share one locality.

A group lists instances of ``person``, ``address`` or ``organization`` that live, or are
located, in the same locality. The localities able to host every member of a group are
known before any generation: a group without one is an invalid template.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fakeverse.engine.index import LocalityInfo, Pool, UniverseIndex, hosts, locality_weight
from fakeverse.engine.template import CompiledTemplate, Instance, compile_template
from fakeverse.errors import InvalidTemplate

COLOCATABLE: Final[tuple[str, ...]] = ("person", "address", "organization")
MIN_GROUP: Final[int] = 2
_REFERENCE = re.compile(r"^(?P<type>[a-z]+)(?:#(?P<n>[1-9]))?$")


@dataclass(frozen=True, slots=True)
class ColocationGroup:
    """Instances sharing a locality, and the localities that can host all of them."""

    instances: tuple[Instance, ...]
    localities: Pool[LocalityInfo]

    @property
    def kind(self) -> str:
        """``kind`` of the seed of the group's locality; independent of the order."""
        members = ",".join(f"{type_id}#{number}" for type_id, number in sorted(self.instances))
        return f"template:colocate:{members}"


def _candidates(index: UniverseIndex, type_id: str) -> list[LocalityInfo]:
    """Localities that can host an instance of ``type_id``, in file order."""
    every = list(index.localities.items)
    if type_id == "address":
        return every
    if type_id == "person":
        return [info for info in every if any(hosts(p.localities, info) for p in index.peoples)]
    if index.organization_name is not None:
        return every
    canonical = index.organizations.items if index.organizations is not None else ()
    return [info for info in every if any(hosts(org.localities, info) for org in canonical)]


def compile_with_groups(
    template: object,
    groups: Sequence[Sequence[object]],
    index: UniverseIndex,
    *,
    max_leaves: int,
) -> tuple[CompiledTemplate, tuple[ColocationGroup, ...]]:
    """Compile a template and its colocation groups, reporting all their errors at once.

    Raises:
        InvalidTemplate: with every faulty path and group reference.
    """
    try:
        compiled = compile_template(template, index, max_leaves=max_leaves)
    except InvalidTemplate as error:
        try:
            compile_groups(groups, None, index)
        except InvalidTemplate as group_error:
            errors = [*error.errors, *group_error.errors]
            raise InvalidTemplate(f"Invalid template: {len(errors)} error(s).", errors) from None
        raise
    return compiled, compile_groups(groups, compiled, index)


def compile_groups(
    groups: Sequence[Sequence[object]], template: CompiledTemplate | None, index: UniverseIndex
) -> tuple[ColocationGroup, ...]:
    """Validate colocation groups against a compiled template.

    Without a template (it is invalid), only the form of the groups is checked.

    Raises:
        InvalidTemplate: with every faulty reference at once.
    """
    errors: list[dict[str, object]] = []
    compiled: list[ColocationGroup] = []
    used: dict[Instance, None] = {}

    def error(path: str, reference: object, reason: str) -> None:
        errors.append({"path": path, "leaf": reference, "reason": reason})

    for g, group in enumerate(groups):
        members: list[Instance] = []
        if len(group) < MIN_GROUP:
            error(f"/colocate/{g}", list(group), "A group needs at least two instances")
            continue
        for m, reference in enumerate(group):
            path = f"/colocate/{g}/{m}"
            match = _REFERENCE.match(reference) if isinstance(reference, str) else None
            if match is None or match["type"] not in COLOCATABLE:
                error(path, reference, f"Expected an instance of {', '.join(COLOCATABLE)}")
                continue
            instance = (match["type"], int(match["n"] or 1))
            if template is not None and instance not in template.instances:
                error(path, reference, "This instance is not used by the template")
            elif instance in used:
                error(path, reference, "An instance belongs to one group at most")
            else:
                used[instance] = None
                members.append(instance)
        if len(members) != len(group) or template is None:
            continue
        shared = list(index.localities.items)
        for type_id, _number in members:
            allowed = _candidates(index, type_id)
            shared = [info for info in shared if any(info is other for other in allowed)]
        if not shared:
            error(f"/colocate/{g}", list(group), "No locality can host all these instances")
            continue
        compiled.append(ColocationGroup(tuple(members), Pool(shared, locality_weight)))
    if errors:
        raise InvalidTemplate(f"Invalid template: {len(errors)} error(s).", errors)
    return tuple(compiled)
