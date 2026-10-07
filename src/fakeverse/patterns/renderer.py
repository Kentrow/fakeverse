"""Renderer of the pattern DSL.

Random tokens consume the generator in the order they appear in the pattern. A field whose
value is null or empty renders as an empty string, and then triggers the cleanup of orphan
separators.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from fakeverse.engine.explain import Leaf
from fakeverse.engine.index import Pool
from fakeverse.locale import resolve
from fakeverse.model import VocabItem
from fakeverse.patterns.parser import (
    DigitsToken,
    FieldToken,
    Filter,
    IntToken,
    LettersToken,
    Pattern,
    Text,
    VocabToken,
)
from fakeverse.rng import Rng

_NOT_SLUG = re.compile(r"[^a-z0-9]")
_SPACES = re.compile(r" {2,}")
_EDGES = " .,-"


@dataclass(frozen=True, slots=True)
class RenderContext:
    """What a rendering needs besides the pattern and its fields."""

    rng: Rng
    locale: str
    default_locale: str
    vocab: Mapping[str, Pool[VocabItem]]


def slugify(value: str) -> str:
    """NFKD normalization, no diacritics, lowercase, only ``[a-z0-9]``; ``x`` if empty."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _NOT_SLUG.sub("", stripped.lower()) or "x"


def apply_filters(value: str, filters: tuple[Filter, ...]) -> str:
    """Apply chained filters, left to right."""
    for name in filters:
        if name == "slug":
            value = slugify(value)
        elif name == "upper":
            value = value.upper()
        elif name == "lower":
            value = value.lower()
        else:
            value = value.title()
    return value


def cleanup(value: str) -> str:
    """Remove the separators left orphan by empty fields, line by line."""
    lines = []
    for raw in value.split("\n"):
        line = raw.replace("..", ".").replace(".@", "@").replace("-@", "@")
        line = _SPACES.sub(" ", line).strip(_EDGES)
        if line:
            lines.append(line)
    return "\n".join(lines)


def render(
    pattern: Pattern,
    fields: Mapping[str, Leaf],
    context: RenderContext,
    *,
    pattern_fallback: bool = False,
) -> Leaf:
    """Render a parsed pattern.

    Args:
        pattern: the variant of the pattern for the requested locale.
        fields: the context fields available to the pattern.
        context: generator, locales and vocabularies.
        pattern_fallback: whether the variant itself is a fallback to another language.

    Returns:
        A leaf whose origin is ``canon`` only if the pattern has no random token and every
        non-null field it uses is canon.
    """
    parts: list[str] = []
    fallback = pattern_fallback
    canon = not pattern.is_random
    empty_field = False
    rng = context.rng
    for segment in pattern.segments:
        if isinstance(segment, Text):
            parts.append(segment.text)
        elif isinstance(segment, FieldToken):
            leaf = fields[segment.name]
            if leaf.value is None or leaf.value == "":
                empty_field = True
                continue
            fallback = fallback or leaf.fallback
            canon = canon and leaf.origin == "canon"
            parts.append(apply_filters(str(leaf.value), segment.filters))
        elif isinstance(segment, VocabToken):
            item = context.vocab[segment.name].draw(rng)
            resolved = resolve(item.value, context.locale, context.default_locale)
            fallback = fallback or resolved.fallback
            parts.append(apply_filters(resolved.value, segment.filters))
        elif isinstance(segment, IntToken):
            parts.append(str(rng.int_between(segment.min, segment.max)))
        elif isinstance(segment, DigitsToken):
            parts.append(rng.digits(segment.count))
        elif isinstance(segment, LettersToken):
            parts.append(rng.letters(segment.count))
    text = "".join(parts)
    if empty_field:
        text = cleanup(text)
    return Leaf(
        value=text,
        origin="canon" if canon else "generated",
        locale=context.default_locale if fallback else context.locale,
        fallback=fallback,
    )
