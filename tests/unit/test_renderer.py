import pytest

from fakeverse.engine.explain import NULL, Leaf
from fakeverse.engine.index import Pool
from fakeverse.model import VocabItem
from fakeverse.patterns import parse_pattern
from fakeverse.patterns.renderer import RenderContext, apply_filters, cleanup, render, slugify
from fakeverse.rng import Rng


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Frodon", "frodon"),
        ("Éowyn", "eowyn"),
        ("Bilbo Baggins", "bilbobaggins"),
        ("Mûmak-42", "mumak42"),
        ("Ærwen", "rwen"),
        ("---", "x"),
        ("", "x"),
    ],
)
def test_slugify(value: str, expected: str) -> None:
    assert slugify(value) == expected


def test_filters_chain_left_to_right() -> None:
    assert apply_filters("éowyn", ("upper",)) == "ÉOWYN"
    assert apply_filters("ÉOWYN", ("lower",)) == "éowyn"
    assert apply_filters("the green dragon", ("title",)) == "The Green Dragon"
    assert apply_filters("Éowyn", ("slug", "upper")) == "EOWYN"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("elrond.@domain", "elrond@domain"),
        ("elrond-@domain", "elrond@domain"),
        ("a..b", "a.b"),
        ("Elrond  ", "Elrond"),
        ("  Elrond", "Elrond"),
        ("Hobbiton, ", "Hobbiton"),
        (", Eriador", "Eriador"),
        ("12 Lane\n Hobbiton\n\nEriador", "12 Lane\nHobbiton\nEriador"),
        ("a   b", "a b"),
        (". Bree -", "Bree"),
    ],
)
def test_cleanup(value: str, expected: str) -> None:
    assert cleanup(value) == expected


def context(seed: int = 0, locale: str = "fr") -> RenderContext:
    vocab = {
        "adjective": Pool([VocabItem(value={"en": "Green", "fr": "Vert"})], lambda i: i.weight),
        "noun": Pool([VocabItem(value={"en": "Dragon"})], lambda i: i.weight),
    }
    return RenderContext(Rng(seed), locale, "en", vocab)


def canon(value: str) -> Leaf:
    return Leaf(value, "canon", "fr")


def test_canon_pattern_with_canon_fields() -> None:
    leaf = render(
        parse_pattern("{first_name} {family_name}"),
        {"first_name": canon("Frodon"), "family_name": canon("Sacquet")},
        context(),
    )
    assert leaf == Leaf("Frodon Sacquet", "canon", "fr", fallback=False)


def test_generated_field_or_random_token_make_a_generated_value() -> None:
    fields = {"first_name": canon("Frodon"), "family_name": Leaf("Took", "generated", "fr")}
    assert render(parse_pattern("{first_name} {family_name}"), fields, context()).origin == (
        "generated"
    )
    assert render(parse_pattern("{first_name}{digits:2}"), fields, context()).origin == (
        "generated"
    )


def test_empty_field_triggers_cleanup_and_does_not_count() -> None:
    leaf = render(
        parse_pattern("{first_name|slug}.{family_name|slug}@shire.me"),
        {"first_name": canon("Elrond"), "family_name": NULL},
        context(),
    )
    assert leaf.value == "elrond@shire.me"
    assert leaf.origin == "canon"


def test_no_cleanup_without_empty_field() -> None:
    leaf = render(parse_pattern("{name}..."), {"name": canon("Wait")}, context())
    assert leaf.value == "Wait..."


def test_fallbacks_propagate() -> None:
    noun = render(parse_pattern("Le {vocab.noun}"), {}, context())
    assert (noun.value, noun.fallback, noun.locale) == ("Le Dragon", True, "en")
    adjective = render(parse_pattern("{vocab.adjective|upper}"), {}, context())
    assert (adjective.value, adjective.fallback) == ("VERT", False)
    variant = render(parse_pattern("x"), {}, context(), pattern_fallback=True)
    assert variant.fallback
    field = render(parse_pattern("{a}"), {"a": Leaf("A", "canon", "en", True)}, context())
    assert field.fallback


def test_random_tokens_are_deterministic() -> None:
    pattern = parse_pattern("{int:1-99}-{digits:3}-{letters:2}")
    first = render(pattern, {}, context(seed=7))
    assert first == render(pattern, {}, context(seed=7))
    assert first.value != render(pattern, {}, context(seed=8)).value
    assert first.origin == "generated"


def test_integer_fields_are_rendered() -> None:
    leaf = render(parse_pattern("crew: {crew}"), {"crew": Leaf(12, "generated", "fr")}, context())
    assert leaf.value == "crew: 12"
