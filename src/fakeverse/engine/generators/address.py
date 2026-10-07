"""Generator of the ``address`` core type."""

from __future__ import annotations

from fakeverse.engine.explain import NULL, Leaf, Node
from fakeverse.engine.generators.common import Draw
from fakeverse.engine.index import LocalityInfo, Pool


def place_fields(draw: Draw, info: LocalityInfo) -> dict[str, Leaf]:
    """Return the ``locality``, ``subdivision`` and ``area`` context fields of a locality."""
    subdivision = info.subdivision
    return {
        "locality": draw.text(info.place.name, canon=info.place.canon),
        "subdivision": (
            NULL if subdivision is None else draw.text(subdivision.name, canon=subdivision.canon)
        ),
        "area": draw.text(info.area.name, canon=info.area.canon),
    }


def generate_address(
    draw: Draw, localities: Pool[LocalityInfo]
) -> tuple[dict[str, Node], LocalityInfo, dict[str, Leaf]]:
    """Generate an address in one of ``localities``.

    1. Draw a locality, weighted. 2. Resolve its ancestors. 3. Render ``street_address``,
    ``postal_code`` then ``formatted``, each with the override of the nearest place.

    Returns:
        The address, the locality drawn and its place fields, which callers reuse as pattern
        context.
    """
    info = localities.draw(draw.rng)
    places = place_fields(draw, info)
    if info.street_address is None:  # pragma: no cover - excluded by the capabilities
        raise ValueError(f"locality {info.place.id!r} has no street_address pattern")
    street = draw.render(info.street_address, places)
    postal = draw.render_optional(info.postal_code, places)
    formatted = draw.render(
        info.address_format, {**places, "street_address": street, "postal_code": postal}
    )
    address: dict[str, Node] = {
        "street_address": street,
        "postal_code": postal,
        "locality": places["locality"],
        "subdivision": places["subdivision"],
        "area": places["area"],
        "formatted": formatted,
    }
    return address, info, places
