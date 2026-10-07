import pytest
from faker import Faker
from faker.exceptions import UniquenessException

from fakeverse.errors import LocaleNotSupported
from fakeverse.faker import FakeverseProvider, shared_fakeverse
from fakeverse.types import ATOMIC_ALIASES, COMPOSITES


def faker(locale: str = "en_US") -> Faker:
    fake = Faker(locale)
    fake.add_provider(FakeverseProvider)
    return fake


def test_one_item_per_call_for_every_core_type() -> None:
    lotr = faker().fakeverse("lotr")
    for composite in COMPOSITES:
        value = getattr(lotr, composite)()
        assert list(value) == [field.name for field in COMPOSITES[composite]]
    for alias in ATOMIC_ALIASES:
        value = getattr(lotr, alias)()
        assert value is None or isinstance(value, str), alias
    assert set(lotr.generate("weapon")) == {"name", "kind"}


def test_faker_seed_makes_sequences_reproducible() -> None:
    Faker.seed(123)
    first = faker("fr_FR").fakeverse("lotr")
    sequence = [first.full_name() for _ in range(5)]
    Faker.seed(123)
    again = faker("fr_FR").fakeverse("lotr")
    assert [again.full_name() for _ in range(5)] == sequence
    assert len(set(sequence)) > 1


def test_seed_instance() -> None:
    fake = faker()
    fake.seed_instance(9)
    values = [fake.fakeverse("lotr").first_name() for _ in range(3)]
    fake.seed_instance(9)
    assert [fake.fakeverse("lotr").first_name() for _ in range(3)] == values


@pytest.mark.parametrize(
    ("faker_locale", "expected"),
    [("fr_FR", "fr-FR"), ("fr_CA", "fr-CA"), ("en_GB", "en-GB"), ("de_DE", "en"), ("ja_JP", "en")],
)
def test_locale_conversion_and_permissive_fallback(faker_locale: str, expected: str) -> None:
    assert faker(faker_locale).fakeverse("lotr").locale == expected


def test_french_values() -> None:
    lotr = faker("fr_FR").fakeverse("lotr")
    Faker.seed(4)
    names = {lotr.locality() for _ in range(200)}
    assert "Hobbitebourg" in names or "Fondcombe" in names
    assert "Hobbiton" not in names


def test_strict_locale_and_explicit_locale() -> None:
    fake = faker("de_DE")
    with pytest.raises(LocaleNotSupported):
        fake.fakeverse("lotr", strict_locale=True)
    assert fake.fakeverse("lotr", locale="fr").locale == "fr"
    assert fake.fakeverse("lotr", locale="fr", strict_locale=True).locale == "fr"


def test_options_and_template() -> None:
    lotr = faker().fakeverse("lotr")
    assert lotr.person(gender="feminine", people="elf")["people"] == "Elf"
    assert lotr.first_name(explain=True)["origin"] == "canon"
    row = lotr.template({"name": "person.full_name", "town": "person.address.locality"})
    assert list(row) == ["name", "town"]


def test_unique() -> None:
    # Faker's unique proxy needs hashable values, i.e. atomic types.
    lotr = faker().fakeverse("lotr")
    areas = {lotr.unique.area() for _ in range(6)}
    assert len(areas) == 6
    with pytest.raises(UniquenessException):
        lotr.unique.area()
    lotr.unique.clear()
    assert lotr.unique.area()
    names = [lotr.unique.first_name() for _ in range(50)]
    assert len(set(names)) == 50


def test_bound_universes_and_data_are_shared() -> None:
    fake = faker()
    assert fake.fakeverse("lotr") is fake.fakeverse("lotr")
    assert fake.fakeverse("lotr").id == "lotr"
    assert shared_fakeverse() is shared_fakeverse()


def test_unknown_locale_configuration_defaults_to_english() -> None:
    fake = faker()
    provider = next(p for p in fake.providers if isinstance(p, FakeverseProvider))
    provider.generator._Generator__config = {}  # type: ignore[attr-defined]
    assert provider.faker_locale() == "en_US"
