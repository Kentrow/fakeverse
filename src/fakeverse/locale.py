"""Locale handling: validation, normalization and fallback resolution.

Fakeverse accepts the BCP-47 subset ``language[-Script][-REGION]``. The canonical form uses a
lowercase language, a titlecase script and an uppercase region, for instance ``fr``, ``fr-FR``
or ``zh-Hant-TW``.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

CANONICAL_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|[0-9]{3}))?$")

_LOOSE_LOCALE = re.compile(
    r"^(?P<lang>[A-Za-z]{2,3})"
    r"(?:[-_](?P<script>[A-Za-z]{4}))?"
    r"(?:[-_](?P<region>[A-Za-z]{2}|[0-9]{3}))?$"
)

type LocalizedValue = str | dict[str, str]
"""A localized text: a plain string, or a mapping from locale to string."""


def is_canonical_locale(value: str) -> bool:
    """Return whether ``value`` is a locale in canonical form."""
    return CANONICAL_LOCALE.match(value) is not None


def normalize_locale(value: str) -> str:
    """Return the canonical form of a locale.

    ``fr_FR``, ``FR-fr`` and ``fr-fr`` all become ``fr-FR``; ``fr`` stays ``fr``.

    Raises:
        ValueError: if ``value`` is not a locale of the accepted BCP-47 subset.
    """
    match = _LOOSE_LOCALE.match(value)
    if match is None:
        raise ValueError(f"Invalid locale {value!r}: expected language[-Script][-REGION].")
    parts = [match["lang"].lower()]
    if match["script"]:
        parts.append(match["script"].title())
    if match["region"]:
        parts.append(match["region"].upper())
    return "-".join(parts)


def language_of(locale: str) -> str:
    """Return the language subtag of a canonical locale (``fr-CA`` gives ``fr``)."""
    return locale.split("-", 1)[0]


def is_locale_supported(locale: str, declared: Sequence[str]) -> bool:
    """Return whether the language of ``locale`` is the language of a declared locale."""
    language = language_of(locale)
    return any(language_of(candidate) == language for candidate in declared)


@dataclass(frozen=True, slots=True)
class Resolved:
    """Result of the resolution of a localized value."""

    value: str
    locale: str | None
    """Locale key that provided the value, or None for a plain string."""
    fallback: bool
    """Whether the resolution is a counted fallback (a change of language)."""


def resolve(value: LocalizedValue, locale: str, default_locale: str) -> Resolved:
    """Resolve a localized value for a canonical ``locale``.

    The fallback chain is: exact locale, language only, then ``default_locale``. Only a
    change of language counts as a fallback; a plain string never does.

    Raises:
        KeyError: if no key of the chain is present (a valid universe always has
            ``default_locale``).
    """
    if isinstance(value, str):
        return Resolved(value, None, fallback=False)
    language = language_of(locale)
    for candidate in (locale, language):
        if candidate in value:
            return Resolved(value[candidate], candidate, fallback=False)
    fallback = language != language_of(default_locale)
    return Resolved(value[default_locale], default_locale, fallback=fallback)


def is_covered(value: LocalizedValue, locale: str, default_locale: str) -> bool:
    """Return whether ``value`` resolves for ``locale`` without a counted fallback."""
    if isinstance(value, str):
        return True
    language = language_of(locale)
    return locale in value or language in value or language == language_of(default_locale)
