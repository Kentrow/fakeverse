"""State shared by the generators of one item."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from fakeverse.engine.explain import NULL, Leaf
from fakeverse.engine.index import LocalizedPattern, UniverseIndex
from fakeverse.locale import LocalizedValue, resolve
from fakeverse.patterns.renderer import RenderContext, render
from fakeverse.rng import Rng


@dataclass(frozen=True, slots=True)
class Draw:
    """The universe, generator and locale of the item being generated."""

    index: UniverseIndex
    rng: Rng
    locale: str

    def text(self, value: LocalizedValue, *, canon: bool) -> Leaf:
        """Resolve a localized text drawn from an entity or a name."""
        resolved = resolve(value, self.locale, self.index.default_locale)
        return Leaf(
            value=resolved.value,
            origin="canon" if canon else "generated",
            locale=self.index.default_locale if resolved.fallback else self.locale,
            fallback=resolved.fallback,
        )

    def integer(self, value: int, *, canon: bool) -> Leaf:
        """Wrap an integer value."""
        return Leaf(value, "canon" if canon else "generated", self.locale)

    def render(self, pattern: LocalizedPattern, fields: Mapping[str, Leaf]) -> Leaf:
        """Render a localized pattern with the given context fields."""
        variant, fallback = pattern.resolve(self.locale, self.index.default_locale)
        context = RenderContext(
            rng=self.rng,
            locale=self.locale,
            default_locale=self.index.default_locale,
            vocab=self.index.vocab,
        )
        return render(variant, fields, context, pattern_fallback=fallback)

    def render_optional(self, pattern: LocalizedPattern | None, fields: Mapping[str, Leaf]) -> Leaf:
        """Render the pattern of a nullable value: null without pattern or when it renders empty."""
        if pattern is None:
            return NULL
        leaf = self.render(pattern, fields)
        return NULL if leaf.value == "" else leaf
