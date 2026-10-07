"""Parser of the pattern DSL.

A pattern is a string with tokens between braces; everything else is literal, and
``{{`` and ``}}`` produce literal braces. Tokens:

- ``{vocab.NAME}``: weighted draw in a vocabulary;
- ``{int:MIN-MAX}``: uniform integer, ``0 <= MIN <= MAX <= 10**9``;
- ``{digits:N}`` and ``{letters:N}``: ``1 <= N <= 20`` digits or uppercase letters;
- ``{field}``: a field of the current context.

Fields and vocabularies accept chained filters: ``|slug``, ``|upper``, ``|lower``, ``|title``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

type Filter = Literal["slug", "upper", "lower", "title"]

FILTERS: Final[tuple[Filter, ...]] = ("slug", "upper", "lower", "title")
MAX_INT: Final[int] = 10**9
MAX_LENGTH: Final[int] = 20

_NAME = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"
_REFERENCE = re.compile(
    rf"^(?:vocab\.(?P<vocab>{_NAME})|(?P<field>{_NAME}))(?P<filters>(?:\|\w+)*)$"
)
_INT = re.compile(r"^int:(?P<min>\d+)-(?P<max>\d+)$")
_SIZED = re.compile(r"^(?P<kind>digits|letters):(?P<n>\d+)$")


class PatternSyntaxError(ValueError):
    """A pattern is syntactically invalid."""


@dataclass(frozen=True, slots=True)
class Text:
    """Literal text."""

    text: str


@dataclass(frozen=True, slots=True)
class FieldToken:
    """``{field|filters}``: a context field."""

    name: str
    filters: tuple[Filter, ...] = ()


@dataclass(frozen=True, slots=True)
class VocabToken:
    """``{vocab.NAME|filters}``: a weighted draw in a vocabulary."""

    name: str
    filters: tuple[Filter, ...] = ()


@dataclass(frozen=True, slots=True)
class IntToken:
    """``{int:MIN-MAX}``: a uniform integer."""

    min: int
    max: int


@dataclass(frozen=True, slots=True)
class DigitsToken:
    """``{digits:N}``: N random digits."""

    count: int


@dataclass(frozen=True, slots=True)
class LettersToken:
    """``{letters:N}``: N random uppercase letters."""

    count: int


type Segment = Text | FieldToken | VocabToken | IntToken | DigitsToken | LettersToken


@dataclass(frozen=True, slots=True)
class Pattern:
    """A parsed pattern."""

    source: str
    segments: tuple[Segment, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        """Context fields used, in order of first appearance."""
        return tuple(dict.fromkeys(s.name for s in self.segments if isinstance(s, FieldToken)))

    @property
    def vocabs(self) -> tuple[str, ...]:
        """Vocabularies used, in order of first appearance."""
        return tuple(dict.fromkeys(s.name for s in self.segments if isinstance(s, VocabToken)))

    @property
    def is_random(self) -> bool:
        """Whether the pattern contains a random token (vocab, int, digits, letters)."""
        return any(
            isinstance(s, VocabToken | IntToken | DigitsToken | LettersToken) for s in self.segments
        )


def parse_pattern(source: str) -> Pattern:
    """Parse a pattern.

    Raises:
        PatternSyntaxError: if the pattern is invalid. The message names the offending
            token and its position.
    """
    segments: list[Segment] = []
    literal: list[str] = []
    i = 0
    length = len(source)
    while i < length:
        char = source[i]
        if char == "{":
            if source.startswith("{{", i):
                literal.append("{")
                i += 2
                continue
            end = source.find("}", i + 1)
            if end == -1:
                raise PatternSyntaxError(f"Unclosed '{{' at position {i}")
            body = source[i + 1 : end]
            if "{" in body:
                raise PatternSyntaxError(f"Unexpected '{{' inside a token at position {i}")
            if literal:
                segments.append(Text("".join(literal)))
                literal = []
            segments.append(_parse_token(body, i))
            i = end + 1
        elif char == "}":
            if source.startswith("}}", i):
                literal.append("}")
                i += 2
                continue
            raise PatternSyntaxError(f"Unmatched '}}' at position {i}; use '}}}}' for a literal")
        else:
            literal.append(char)
            i += 1
    if literal:
        segments.append(Text("".join(literal)))
    return Pattern(source, tuple(segments))


def _parse_token(body: str, position: int) -> Segment:
    where = f"token '{{{body}}}' at position {position}"
    if not body:
        raise PatternSyntaxError(f"Empty token at position {position}")
    if match := _INT.match(body):
        low, high = int(match["min"]), int(match["max"])
        if not low <= high <= MAX_INT:
            raise PatternSyntaxError(f"Invalid range in {where}: expected 0 <= MIN <= MAX <= 10^9")
        return IntToken(low, high)
    if match := _SIZED.match(body):
        count = int(match["n"])
        if not 1 <= count <= MAX_LENGTH:
            raise PatternSyntaxError(f"Invalid length in {where}: expected 1 <= N <= 20")
        return DigitsToken(count) if match["kind"] == "digits" else LettersToken(count)
    if match := _REFERENCE.match(body):
        filters = _parse_filters(match["filters"], where)
        if match["vocab"] is not None:
            return VocabToken(match["vocab"], filters)
        return FieldToken(match["field"], filters)
    raise PatternSyntaxError(f"Invalid {where}")


def _parse_filters(raw: str, where: str) -> tuple[Filter, ...]:
    filters: list[Filter] = []
    for name in raw.split("|")[1:]:
        for known in FILTERS:
            if name == known:
                filters.append(known)
                break
        else:
            expected = ", ".join(FILTERS)
            raise PatternSyntaxError(f"Unknown filter '{name}' in {where}; expected {expected}")
    return tuple(filters)
