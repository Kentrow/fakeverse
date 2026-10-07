"""Generator of extension types."""

from __future__ import annotations

from fakeverse.engine.explain import Leaf, Node
from fakeverse.engine.generators.common import Draw
from fakeverse.engine.index import ExtensionInfo


def generate_extension(draw: Draw, info: ExtensionInfo) -> dict[str, Node]:
    """Generate an item of an extension.

    ``items`` form: ``{"name": ..., <fields...>}`` of a weighted draw among the items.
    ``fields`` form: each field in declaration order; a pattern sees the fields before it.
    """
    if info.items is not None:
        item = info.items.draw(draw.rng)
        result: dict[str, Leaf] = {"name": draw.text(item.name, canon=item.canon)}
        for key, value in item.fields.items():
            result[key] = (
                draw.integer(value, canon=item.canon)
                if isinstance(value, int)
                else draw.text(value, canon=item.canon)
            )
        return dict(result)

    index = draw.index
    fields: dict[str, Leaf] = {}
    for key, spec in (info.extension.fields or {}).items():
        if spec.pattern is not None:
            fields[key] = draw.render(info.patterns[key], fields)
        elif spec.vocab is not None:
            entry = index.vocab[spec.vocab].draw(draw.rng)
            fields[key] = draw.text(entry.value, canon=False)
        elif spec.place is not None:
            place = index.places_by_level[spec.place].draw(draw.rng)
            fields[key] = draw.text(place.name, canon=place.canon)
        elif spec.people is not None:
            people = index.people_pool.draw(draw.rng).people
            fields[key] = draw.text(people.name, canon=people.canon)
        else:
            low, high = spec.bounds or (0, 0)
            fields[key] = draw.integer(draw.rng.int_between(low, high), canon=False)
    return dict(fields)
