"""Exception hierarchy of Fakeverse.

Every exception carries a stable ``slug``, reused by the HTTP API as the problem type
(``/problems/<slug>``), and a short human-readable ``title``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from fakeverse.validation import Issue


class FakeverseError(Exception):
    """Base class of all Fakeverse errors."""

    slug: ClassVar[str] = "fakeverse-error"
    title: ClassVar[str] = "Fakeverse error"


class UniverseNotFound(FakeverseError):
    """The requested universe does not exist or is disabled."""

    slug = "universe-not-found"
    title = "Universe not found"


class TypeNotSupported(FakeverseError):
    """The requested type is unknown or not supported by the universe."""

    slug = "type-not-supported"
    title = "Type not supported"


class LocaleNotSupported(FakeverseError):
    """The language of the requested locale is not supported by the universe."""

    slug = "locale-not-supported"
    title = "Locale not supported"


class InvalidOption(FakeverseError):
    """An option is invalid or not applicable to the requested type."""

    slug = "invalid-parameter"
    title = "Invalid parameter"


class InvalidTemplate(FakeverseError):
    """A template is invalid.

    ``errors`` lists every faulty leaf: ``{"path": <JSON pointer>, "leaf": ..., "reason": ...}``.
    """

    slug = "invalid-template"
    title = "Invalid template"

    def __init__(self, message: str, errors: Sequence[dict[str, object]] = ()) -> None:
        super().__init__(message)
        self.errors: list[dict[str, object]] = list(errors)


class PoolExhausted(FakeverseError):
    """Uniqueness cannot be satisfied with the available data.

    ``unique_count`` is the number of unique items obtained before giving up.
    """

    slug = "pool-exhausted"
    title = "Pool exhausted"

    def __init__(self, message: str, unique_count: int = 0) -> None:
        super().__init__(message)
        self.unique_count = unique_count


class DataVersionNotFound(FakeverseError):
    """The requested data version is unknown."""

    slug = "data-version-not-found"
    title = "Data version not found"


class DataVersionRetired(FakeverseError):
    """The requested data version was produced by an older engine revision."""

    slug = "data-version-retired"
    title = "Data version retired"


class UniverseValidationError(FakeverseError):
    """One or more universe files are invalid.

    ``issues`` holds the complete list of problems found, errors and warnings alike.
    """

    slug = "universe-validation-error"
    title = "Universe validation error"

    def __init__(self, issues: Sequence[Issue]) -> None:
        self.issues: tuple[Issue, ...] = tuple(issues)
        errors = [issue for issue in self.issues if issue.severity == "error"]
        lines = [f"{len(errors)} error(s) in universe files:"]
        lines.extend(f"  {issue.format()}" for issue in errors)
        super().__init__("\n".join(lines))
