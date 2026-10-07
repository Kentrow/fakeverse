import pytest

from fakeverse.patterns import (
    DigitsToken,
    FieldToken,
    IntToken,
    LettersToken,
    PatternSyntaxError,
    Text,
    VocabToken,
    parse_pattern,
)


def test_parse_every_token() -> None:
    pattern = parse_pattern(
        "{int:1-99} {vocab.street_type|title} {digits:4}-{letters:2} {first_name|slug|upper}"
    )
    assert pattern.segments == (
        IntToken(1, 99),
        Text(" "),
        VocabToken("street_type", ("title",)),
        Text(" "),
        DigitsToken(4),
        Text("-"),
        LettersToken(2),
        Text(" "),
        FieldToken("first_name", ("slug", "upper")),
    )


def test_literal_only_and_escaped_braces() -> None:
    assert parse_pattern("plain text").segments == (Text("plain text"),)
    assert parse_pattern("{{x}} {y}").segments == (Text("{x} "), FieldToken("y"))
    assert parse_pattern("").segments == ()


def test_properties() -> None:
    pattern = parse_pattern("{first_name}.{family_name}@{vocab.domain} {first_name}")
    assert pattern.fields == ("first_name", "family_name")
    assert pattern.vocabs == ("domain",)
    assert pattern.is_random
    assert not parse_pattern("{first_name} {family_name}").is_random
    assert parse_pattern("{digits:2}").is_random


def test_bounds_are_inclusive() -> None:
    assert parse_pattern("{int:0-1000000000}").segments == (IntToken(0, 10**9),)
    assert parse_pattern("{int:5-5}").segments == (IntToken(5, 5),)
    assert parse_pattern("{digits:20}{letters:1}").segments == (DigitsToken(20), LettersToken(1))


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("{first_name", "Unclosed"),
        ("first_name}", "Unmatched"),
        ("{{a}", "Unmatched"),
        ("{a{b}}", "inside a token"),
        ("{}", "Empty token"),
        ("{int:9-1}", "Invalid range"),
        ("{int:0-1000000001}", "Invalid range"),
        ("{int:-1-5}", "Invalid token"),
        ("{digits:0}", "Invalid length"),
        ("{letters:21}", "Invalid length"),
        ("{first_name|shout}", "Unknown filter 'shout'"),
        ("{first_name|}", "Invalid token"),
        ("{First}", "Invalid token"),
        ("{vocab.}", "Invalid token"),
        ("{first name}", "Invalid token"),
        ("{int:1-5|upper}", "Invalid token"),
    ],
)
def test_syntax_errors(source: str, message: str) -> None:
    with pytest.raises(PatternSyntaxError, match=message):
        parse_pattern(source)
