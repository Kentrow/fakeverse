import pytest

from fakeverse.locale import (
    is_canonical_locale,
    is_covered,
    is_locale_supported,
    language_of,
    normalize_locale,
    resolve,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("fr", "fr"),
        ("FR", "fr"),
        ("fr_FR", "fr-FR"),
        ("FR-fr", "fr-FR"),
        ("fr-fr", "fr-FR"),
        ("zh_hant_tw", "zh-Hant-TW"),
        ("es-419", "es-419"),
        ("ast", "ast"),
    ],
)
def test_normalize_locale(raw: str, expected: str) -> None:
    assert normalize_locale(raw) == expected
    assert is_canonical_locale(expected)


@pytest.mark.parametrize("raw", ["", "f", "francais", "fr-", "fr-FRA", "fr--FR", "fr-FR-x"])
def test_normalize_locale_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError, match="Invalid locale"):
        normalize_locale(raw)


@pytest.mark.parametrize("value", ["fr_FR", "fr-fr", "FR", "zh-hant"])
def test_non_canonical_forms(value: str) -> None:
    assert not is_canonical_locale(value)


def test_language_of() -> None:
    assert language_of("fr-CA") == "fr"
    assert language_of("zh-Hant-TW") == "zh"
    assert language_of("en") == "en"


def test_is_locale_supported_compares_languages() -> None:
    assert is_locale_supported("fr-CA", ["en", "fr"])
    assert is_locale_supported("fr", ["en", "fr-FR"])
    assert not is_locale_supported("de", ["en", "fr"])


def test_resolve_plain_string_is_never_a_fallback() -> None:
    resolved = resolve("Elrond", "fr", "en")
    assert (resolved.value, resolved.locale, resolved.fallback) == ("Elrond", None, False)


def test_resolve_chain() -> None:
    value = {"en": "Baggins", "fr": "Sacquet", "fr-CA": "Sacquet-CA"}
    assert resolve(value, "fr-CA", "en").value == "Sacquet-CA"
    assert resolve(value, "fr-BE", "en").locale == "fr"
    assert not resolve(value, "fr-BE", "en").fallback


def test_resolve_counts_language_fallback_only() -> None:
    value = {"en": "Baggins"}
    fallback = resolve(value, "fr", "en")
    assert (fallback.value, fallback.locale, fallback.fallback) == ("Baggins", "en", True)
    same_language = resolve(value, "en-GB", "en")
    assert not same_language.fallback


def test_resolve_regional_default_locale() -> None:
    value = {"en-US": "Color"}
    assert not resolve(value, "en-GB", "en-US").fallback
    assert resolve(value, "fr", "en-US").fallback


def test_is_covered() -> None:
    assert is_covered("Plain", "fr", "en")
    assert is_covered({"en": "A", "fr": "B"}, "fr-CA", "en")
    assert not is_covered({"en": "A"}, "fr", "en")
    assert is_covered({"en-US": "A"}, "en-GB", "en-US")
