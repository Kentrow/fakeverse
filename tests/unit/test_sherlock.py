"""Invariants specific to the sherlock universe (see the design in docs/superpowers/specs)."""

import pytest

from fakeverse import Fakeverse

FV = Fakeverse()
DISTRICTS = {"W", "NW", "WC", "EC", "E", "SW", "SE", "N"}


def items(type_id: str, count: int = 300, locale: str = "en", **options: object) -> list:
    return (
        FV.universe("sherlock", locale)
        .generate(type_id, count, seed=1, unique=False, **options)
        .items
    )


@pytest.mark.parametrize(("locale", "city"), [("en", "London"), ("fr", "Londres")])
def test_london_address_format(locale: str, city: str) -> None:
    london = [a for a in items("address", locale=locale) if a["subdivision"] == city]
    assert london
    for a in london:
        assert a["postal_code"] in DISTRICTS
        assert (
            a["formatted"] == f"{a['street_address']}\n{a['locality']}, {city} {a['postal_code']}"
        )


@pytest.mark.parametrize(
    ("locality", "district"),
    [
        ("Marylebone", "W"),
        ("Bloomsbury", "WC"),
        ("The City", "EC"),
        ("Whitechapel", "E"),
        ("St John's Wood", "NW"),
        ("Lambeth", "SE"),
        ("Westminster", "SW"),
        ("Islington", "N"),
    ],
)
def test_london_district_matches_neighbourhood(locality: str, district: str) -> None:
    found = [a for a in items("address", 2000) if a["locality"] == locality]
    assert found and {a["postal_code"] for a in found} == {district}


def test_addresses_outside_london_name_their_region() -> None:
    others = [a for a in items("address") if a["subdivision"] != "London"]
    assert others
    for a in others:
        assert a["postal_code"] is None
        assert a["formatted"].endswith(f"\n{a['subdivision']}, {a['area']}")
