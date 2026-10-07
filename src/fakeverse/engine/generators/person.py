"""Generator of the ``person`` core type."""

from __future__ import annotations

from fakeverse.engine.explain import NULL, Leaf, Node
from fakeverse.engine.generators.address import generate_address
from fakeverse.engine.generators.common import Draw
from fakeverse.engine.index import (
    LocalityInfo,
    PeopleInfo,
    Pool,
    hosts,
    locality_weight,
    people_weight,
)
from fakeverse.types import Gender


def generate_person(
    draw: Draw,
    peoples: Pool[PeopleInfo],
    gender: Gender | None,
    locality: LocalityInfo | None = None,
) -> dict[str, Node]:
    """Generate a person.

    Args:
        draw: the item being generated.
        peoples: the peoples compatible with the options (see
            :meth:`~fakeverse.engine.index.UniverseIndex.eligible_peoples`).
        gender: the imposed gender, if any.
        locality: imposed locality (template colocation); only the peoples whose homelands
            contain it are drawn. The caller guarantees that there is at least one.
    """
    rng = draw.rng
    if locality is not None:
        peoples = Pool(
            [info for info in peoples.items if hosts(info.localities, locality)],
            people_weight,
        )
    # 1. People.
    info = peoples.draw(rng)
    people = info.people
    # 2. Gender: imposed, or drawn among the genders of the first names.
    if gender is None and info.genders is not None:
        gender = info.genders.draw(rng)[0]
    # 3. First name, of that gender or without gender.
    first = info.first_names[gender].draw(rng)
    # 4. Family name.
    family = None if info.family_names is None else info.family_names.draw(rng)
    # 5. Address in the homelands (or the imposed locality).
    homes = info.localities if locality is None else Pool([locality], locality_weight)
    address, locality, places = generate_address(draw, homes)

    first_name = draw.text(first.value, canon=first.canon)
    last_name = NULL if family is None else draw.text(family.value, canon=family.canon)
    fields: dict[str, Leaf] = {
        "first_name": first_name,
        "family_name": last_name,
        "people": draw.text(people.name, canon=people.canon),
        **places,
    }
    index = draw.index
    # 6. Full name, then 7. email, username and phone.
    full_name = draw.render(info.name_format, fields)
    email = draw.render_optional(index.email, fields)
    username = draw.render_optional(index.username, fields)
    phone = draw.render_optional(locality.phone, places)
    return {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "gender": NULL if gender is None else Leaf(gender, first_name.origin, draw.locale),
        "people": fields["people"],
        "address": address,
        "email": email,
        "username": username,
        "phone": phone,
    }
