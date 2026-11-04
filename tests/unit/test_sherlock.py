"""Invariants specific to the sherlock universe (see the design in docs/superpowers/specs)."""

import re

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


def test_americans_live_in_the_united_states() -> None:
    assert {p["address"]["area"] for p in items("person", people="american")} == {"United States"}


def test_vermissa_exists() -> None:
    assert "Vermissa" in {a["locality"] for a in items("address", 3000)}


PEOPLES = ["english", "american", "scottish", "irish"]


def test_the_irish_never_live_in_vermissa() -> None:
    assert all(
        p["address"]["subdivision"] != "Vermissa Valley"
        for p in items("person", 2000, people="irish")
    )


@pytest.mark.parametrize("people", PEOPLES)
@pytest.mark.parametrize("gender", ["masculine", "feminine"])
def test_every_people_and_gender_generates(people: str, gender: str) -> None:
    assert all(p["gender"] == gender for p in items("person", 20, people=people, gender=gender))


@pytest.mark.parametrize("people", PEOPLES)
def test_emails_are_valid(people: str) -> None:
    for p in items("person", 500, people=people):
        assert re.fullmatch(
            r"[a-z0-9]+(\.[a-z0-9]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*\.example", p["email"]
        )


def test_invented_names_are_generated() -> None:
    result = FV.universe("sherlock").generate(
        "first_name", 500, seed=1, unique=False, people="irish", explain=True
    )
    assert "generated" in {value["origin"] for value in result.items}


def test_canonical_organizations() -> None:
    names = {o["name"] for o in items("organization", 3000)}
    assert {"The Diogenes Club", "The Red-Headed League", "The Alpha Inn"} <= names
    assert not any("Freemen" in n or "Scowrer" in n for n in names)


def test_generated_organizations_have_two_different_partners() -> None:
    for o in items("organization", 1000):
        if " & " in o["name"]:
            senior, junior = o["name"].split(" & ", 1)
            assert senior != junior


COLLECTIONS = {
    "Novel",
    "The Adventures of Sherlock Holmes",
    "The Memoirs of Sherlock Holmes",
    "The Return of Sherlock Holmes",
    "His Last Bow",
    "The Case-Book of Sherlock Holmes",
}


def test_the_sixty_cases() -> None:
    assert len(FV.universe("sherlock").index.extensions["case"].items.items) == 60
    novels = [c for c in items("case", 3000) if c["collection"] == "Novel"]
    assert {c["name"] for c in novels} == {
        "A Study in Scarlet",
        "The Sign of the Four",
        "The Hound of the Baskervilles",
        "The Valley of Fear",
    }
    for c in items("case", 500):
        assert c["collection"] in COLLECTIONS
        assert 1887 <= c["year"] <= 1927


def test_inspectors() -> None:
    names = {i["name"] for i in items("inspector", 1000)}
    assert {"Lestrade", "Gregson", "Athelney Jones", "Stanley Hopkins"} <= names
