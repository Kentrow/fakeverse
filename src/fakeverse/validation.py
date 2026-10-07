"""Validation of universe files.

Rule numbers refer to the validation rules of ``docs/universe-guide.md``.

Validation runs in three stages:

1. raw checks on the parsed YAML data (string length);
2. structural checks by the Pydantic models of :mod:`fakeverse.model`;
3. semantic checks on a structurally valid universe (references, hierarchy, locales,
   patterns, minimum data, extensions), followed by the warnings.

Each problem is an :class:`Issue` with a stable ``code``, the YAML path of the offending
value and, when known, its line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from pydantic import ValidationError

from fakeverse.capabilities import compute_capabilities
from fakeverse.hierarchy import PlaceTree
from fakeverse.locale import LocalizedValue, is_canonical_locale, is_covered, normalize_locale
from fakeverse.model import UniverseFile
from fakeverse.patterns import Pattern, PatternSyntaxError, Text, parse_pattern
from fakeverse.types import NAME_FORMAT_CONTEXT, PATTERN_CONTEXT, RESERVED_TYPE_IDS

type Severity = Literal["error", "warning"]
type PathPart = str | int
type Path = tuple[PathPart, ...]

MAX_STRING_LENGTH: Final[int] = 80
MAX_SOURCES_LENGTH: Final[int] = 200
MIN_FIRST_NAMES: Final[int] = 10
COVERAGE_EXAMPLES: Final[int] = 5


def format_path(path: Path) -> str:
    """Format a YAML path as ``places[12].parent``; the root is ``<root>``."""
    text = ""
    for part in path:
        if isinstance(part, int):
            text += f"[{part}]"
        else:
            text += f".{part}" if text else part
    return text or "<root>"


@dataclass(frozen=True, slots=True)
class Issue:
    """A validation problem."""

    severity: Severity
    code: str
    """Stable identifier of the rule, e.g. ``unknown-reference``."""
    message: str
    path: Path = ()
    line: int | None = None
    file: str | None = None

    def format(self, *, with_file: bool = True) -> str:
        """Format the issue on one line: ``file:line: path: message [code]``."""
        location = (self.file or "") if with_file else ""
        if self.line is not None:
            location += f":{self.line}" if location else f"line {self.line}"
        prefix = f"{location}: " if location else ""
        return f"{prefix}{format_path(self.path)}: {self.message} [{self.code}]"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "path": format_path(self.path),
            "line": self.line,
        }


@dataclass(slots=True)
class Collector:
    """Accumulates issues, resolving their line through ``line_of``."""

    line_of: Callable[[Path], int | None] = lambda _path: None
    issues: list[Issue] = field(default_factory=list)

    def error(self, code: str, path: Path, message: str) -> None:
        self.issues.append(Issue("error", code, message, path, self.line_of(path)))

    def warning(self, code: str, path: Path, message: str) -> None:
        self.issues.append(Issue("warning", code, message, path, self.line_of(path)))

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def validate_data(
    data: object,
    *,
    expected_id: str | None = None,
    line_of: Callable[[Path], int | None] | None = None,
) -> tuple[UniverseFile | None, list[Issue]]:
    """Validate parsed YAML data of a universe file.

    Args:
        data: the result of ``yaml.safe_load``.
        expected_id: the file name without extension, which must equal ``universe.id``.
        line_of: returns the line of a YAML path, when known.

    Returns:
        The universe when it has no error (it may have warnings), and every issue found.
    """
    collector = Collector(line_of or (lambda _path: None))
    _check_string_lengths(data, (), collector)
    try:
        universe = UniverseFile.model_validate(data)
    except ValidationError as exc:
        for error in exc.errors():
            path = tuple(part for part in error["loc"] if part != "[key]")
            collector.error("schema", path, _schema_message(error))
        return None, collector.issues
    _check_semantics(universe, expected_id, collector)
    if collector.has_errors:
        return None, collector.issues
    _check_warnings(universe, collector)
    return universe, collector.issues


def _schema_message(error: Mapping[str, Any]) -> str:
    loc = error["loc"]
    last = loc[-1] if loc else ""
    if error["type"] == "extra_forbidden":
        return f"Unknown key '{last}'"
    if error["type"] == "missing":
        return f"Missing required key '{last}'"
    if error["type"] == "literal_error" and loc == ("format",):
        return "Unsupported format version; expected 1"
    message: str = error["msg"]
    return message


# Stage 1: raw checks


def _check_string_lengths(value: object, path: Path, collector: Collector) -> None:
    """Rule 11: no string longer than 80 characters (200 under ``universe.sources``)."""
    if isinstance(value, str):
        limit = MAX_SOURCES_LENGTH if path[:2] == ("universe", "sources") else MAX_STRING_LENGTH
        if len(value) > limit:
            collector.error(
                "string-too-long",
                path,
                f"String of {len(value)} characters; the maximum is {limit} "
                "(universe files hold short names and labels only)",
            )
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_string_lengths(key, (*path, str(key)), collector)
            _check_string_lengths(item, (*path, str(key)), collector)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _check_string_lengths(item, (*path, index), collector)


# Traversal helpers


def iter_localized(universe: UniverseFile) -> Iterator[tuple[Path, LocalizedValue]]:
    """Yield every localized value of a universe (texts and patterns) with its path."""
    yield ("universe", "name"), universe.universe.name
    if universe.place_levels is not None:
        for level in ("area", "subdivision", "locality"):
            label: LocalizedValue | None = getattr(universe.place_levels, level)
            if label is not None:
                yield ("place_levels", level), label
    for i, place in enumerate(universe.places):
        yield ("places", i, "name"), place.name
    yield from _iter_people_texts(universe)
    for i, org in enumerate(universe.organizations):
        yield ("organizations", i, "name"), org.name
        if org.kind is not None:
            yield ("organizations", i, "kind"), org.kind
    for name, items in universe.vocab.items():
        for j, item in enumerate(items):
            yield ("vocab", name, j), item.value
    yield from _iter_extension_texts(universe)
    for path, pattern, _allowed in iter_patterns(universe):
        yield path, pattern


def _iter_people_texts(universe: UniverseFile) -> Iterator[tuple[Path, LocalizedValue]]:
    for i, people in enumerate(universe.peoples):
        yield ("peoples", i, "name"), people.name
        for j, first in enumerate(people.first_names):
            yield ("peoples", i, "first_names", j), first.value
        for j, family in enumerate(people.family_names or ()):
            yield ("peoples", i, "family_names", j), family.value


def _iter_extension_texts(universe: UniverseFile) -> Iterator[tuple[Path, LocalizedValue]]:
    for ext_id, ext in universe.extensions.items():
        yield ("extensions", ext_id, "label"), ext.label
        for j, item in enumerate(ext.items or ()):
            yield ("extensions", ext_id, "items", j, "name"), item.name
            for key, value in item.fields.items():
                if not isinstance(value, int):
                    yield ("extensions", ext_id, "items", j, "fields", key), value


def iter_patterns(
    universe: UniverseFile,
) -> Iterator[tuple[Path, LocalizedValue, tuple[str, ...]]]:
    """Yield every pattern with its path and the context fields it may use."""
    for name, allowed in PATTERN_CONTEXT.items():
        pattern: LocalizedValue | None = getattr(universe.patterns, name)
        if pattern is not None:
            yield ("patterns", name), pattern, allowed
    for i, place in enumerate(universe.places):
        if place.patterns is None:
            continue
        for name in type(place.patterns).model_fields:
            override: LocalizedValue | None = getattr(place.patterns, name)
            if override is not None:
                yield ("places", i, "patterns", name), override, PATTERN_CONTEXT[name]
    for i, people in enumerate(universe.peoples):
        if people.name_format is not None:
            yield ("peoples", i, "name_format"), people.name_format, NAME_FORMAT_CONTEXT
    for ext_id, ext in universe.extensions.items():
        declared: list[str] = []
        for key, spec in (ext.fields or {}).items():
            if spec.pattern is not None:
                yield (
                    ("extensions", ext_id, "fields", key, "pattern"),
                    spec.pattern,
                    tuple(declared),
                )
            declared.append(key)


def _variants(path: Path, value: LocalizedValue) -> Iterator[tuple[Path, str]]:
    if isinstance(value, str):
        yield path, value
    else:
        for locale, text in value.items():
            yield (*path, locale), text


# Stage 3: semantic checks


def _check_semantics(universe: UniverseFile, expected_id: str | None, collector: Collector) -> None:
    meta = universe.universe
    if expected_id is not None and meta.id != expected_id:
        collector.error(
            "id-mismatch",
            ("universe", "id"),
            f"Universe id '{meta.id}' must equal the file name '{expected_id}'",
        )
    _check_unique_ids(universe, collector)
    _check_locales(universe, collector)
    references_ok = _check_places(universe, collector)
    _check_peoples_and_organizations(universe, collector, check_localities=references_ok)
    _check_patterns(universe, collector)
    _check_extensions(universe, collector)
    _check_minimum_data(universe, collector)


def _check_unique_ids(universe: UniverseFile, collector: Collector) -> None:
    """Rule 3: ids are unique within each collection."""
    collections: list[tuple[Path, Sequence[Any]]] = [
        (("places",), universe.places),
        (("peoples",), universe.peoples),
        (("organizations",), universe.organizations),
    ]
    collections.extend(
        (("extensions", ext_id, "items"), ext.items)
        for ext_id, ext in universe.extensions.items()
        if ext.items
    )
    for path, entities in collections:
        seen: dict[str, int] = {}
        for index, entity in enumerate(entities):
            if entity.id in seen:
                collector.error(
                    "duplicate-id",
                    (*path, index, "id"),
                    f"Duplicate id '{entity.id}' (first used at "
                    f"{format_path((*path, seen[entity.id]))})",
                )
            else:
                seen[entity.id] = index


def _check_locales(universe: UniverseFile, collector: Collector) -> None:
    """Rules 7 and 8: locales are valid, declared, and localized texts have the default."""
    meta = universe.universe
    declared: list[str] = []
    for index, locale in enumerate(meta.locales):
        path: Path = ("universe", "locales", index)
        if not _check_locale_format(locale, path, collector):
            continue
        if locale in declared:
            collector.error("duplicate-locale", path, f"Locale '{locale}' is declared twice")
        declared.append(locale)
    default_ok = _check_locale_format(
        meta.default_locale, ("universe", "default_locale"), collector
    )
    if default_ok and meta.default_locale not in meta.locales:
        collector.error(
            "locale-not-declared",
            ("universe", "default_locale"),
            f"Default locale '{meta.default_locale}' is not in universe.locales",
        )
    for locale in meta.sources.translations:
        path = ("universe", "sources", "translations", locale)
        if _check_locale_format(locale, path, collector) and locale not in meta.locales:
            collector.error(
                "locale-not-declared", path, f"Locale '{locale}' is not in universe.locales"
            )
    for path, value in iter_localized(universe):
        if isinstance(value, str):
            continue
        for locale in value:
            locale_path = (*path, locale)
            if _check_locale_format(locale, locale_path, collector) and locale not in meta.locales:
                collector.error(
                    "locale-not-declared",
                    locale_path,
                    f"Locale '{locale}' is not in universe.locales",
                )
        if default_ok and meta.default_locale not in value:
            collector.error(
                "missing-default-locale",
                path,
                f"Localized text has no value for the default locale '{meta.default_locale}'",
            )


def _check_locale_format(locale: str, path: Path, collector: Collector) -> bool:
    if is_canonical_locale(locale):
        return True
    try:
        hint = f"; use '{normalize_locale(locale)}'"
    except ValueError:
        hint = ""
    collector.error(
        "invalid-locale",
        path,
        f"Invalid locale '{locale}': expected language[-Script][-REGION] in canonical form{hint}",
    )
    return False


def _check_places(universe: UniverseFile, collector: Collector) -> bool:
    """Rules 4 and 5: parents exist and the hierarchy follows the levels.

    Returns whether the hierarchy is sound enough for the locality checks.
    """
    by_id = {place.id: place for place in reversed(universe.places)}
    ok = True
    for index, place in enumerate(universe.places):
        path: Path = ("places", index, "parent")
        if place.level == "area":
            if place.parent is not None:
                collector.error("place-hierarchy", path, "An area cannot have a parent")
                ok = False
            continue
        if place.parent is None:
            expected = "an area" if place.level == "subdivision" else "a subdivision or an area"
            collector.error(
                "place-hierarchy", path, f"A {place.level} must have {expected} as parent"
            )
            ok = False
            continue
        parent = by_id.get(place.parent)
        if parent is None:
            collector.error("unknown-reference", path, f"Unknown place '{place.parent}'")
            ok = False
            continue
        allowed = ("area",) if place.level == "subdivision" else ("subdivision", "area")
        if parent.level not in allowed:
            collector.error(
                "place-hierarchy",
                path,
                f"The parent of a {place.level} must be {' or '.join(allowed)}, "
                f"not {parent.level} '{parent.id}'",
            )
            ok = False
    return ok


def _check_peoples_and_organizations(
    universe: UniverseFile, collector: Collector, *, check_localities: bool
) -> None:
    """Rules 4 and 6: referenced places exist and contain at least one locality."""
    tree = PlaceTree(universe.places)
    references: list[tuple[Path, str, str]] = []
    for i, people in enumerate(universe.peoples):
        references.extend(
            (("peoples", i, "homelands", j), place_id, "homeland")
            for j, place_id in enumerate(people.homelands)
        )
    for i, org in enumerate(universe.organizations):
        references.extend(
            (("organizations", i, "places", j), place_id, "place")
            for j, place_id in enumerate(org.places)
        )
    for path, place_id, role in references:
        if place_id not in tree.by_id:
            collector.error("unknown-reference", path, f"Unknown place '{place_id}'")
        elif check_localities and not tree.localities_under(place_id):
            collector.error(
                "no-locality",
                path,
                f"The {role} '{place_id}' contains no locality (itself or a descendant)",
            )


def _check_patterns(universe: UniverseFile, collector: Collector) -> None:
    """Rules 4 and 9: patterns parse, and use allowed fields and existing vocabularies."""
    for path, value, allowed in iter_patterns(universe):
        for variant_path, source in _variants(path, value):
            try:
                pattern = parse_pattern(source)
            except PatternSyntaxError as exc:
                collector.error("invalid-pattern", variant_path, str(exc))
                continue
            for name in pattern.fields:
                if name not in allowed:
                    choices = ", ".join(allowed) or "none"
                    collector.error(
                        "pattern-field-not-allowed",
                        variant_path,
                        f"Field '{name}' is not available in this pattern (available: {choices})",
                    )
            for name in pattern.vocabs:
                if name not in universe.vocab:
                    collector.error(
                        "unknown-reference", variant_path, f"Unknown vocabulary '{name}'"
                    )
            never_null = _never_null_fields(universe, path)
            if never_null is not None and _may_render_empty(pattern, never_null):
                collector.error(
                    "pattern-may-be-empty",
                    variant_path,
                    "This pattern can render an empty value: add text, a random token or a "
                    f"field that is never null ({', '.join(never_null)})",
                )


_PLACE_NEVER_NULL: Final[tuple[str, ...]] = ("locality", "area")
_REQUIRED_PATTERNS: Final[dict[str, tuple[str, ...]]] = {
    "street_address": _PLACE_NEVER_NULL,
    "address_format": (*_PLACE_NEVER_NULL, "street_address"),
    "organization_name": _PLACE_NEVER_NULL,
}
_SEPARATORS: Final[str] = " .,-\n"


def _never_null_fields(universe: UniverseFile, path: Path) -> tuple[str, ...] | None:
    """Context fields that are never null, for a pattern whose output must not be empty.

    Returns None for the patterns of nullable outputs (postal code, phone, email, username).
    """
    if path[0] in ("patterns", "places"):
        return _REQUIRED_PATTERNS.get(str(path[-1]))
    if path[0] == "peoples":
        people = universe.peoples[int(path[1])]
        family = ("family_name",) if people.family_names else ()
        return ("first_name", *family, "people", *_PLACE_NEVER_NULL)
    # Extension field pattern: every field declared before it.
    fields = list(universe.extensions[str(path[1])].fields or {})
    return tuple(fields[: fields.index(str(path[3]))])


def _may_render_empty(pattern: Pattern, never_null: tuple[str, ...]) -> bool:
    """Whether a pattern can render an empty string once orphan separators are cleaned."""
    if pattern.is_random or any(name in never_null for name in pattern.fields):
        return False
    return not any(
        char not in _SEPARATORS
        for segment in pattern.segments
        if isinstance(segment, Text)
        for char in segment.text
    )


def _check_extensions(universe: UniverseFile, collector: Collector) -> None:
    """Rule 13 and the consistency of extension definitions."""
    levels = {place.level for place in universe.places}
    for ext_id, ext in universe.extensions.items():
        path: Path = ("extensions", ext_id)
        if ext_id in RESERVED_TYPE_IDS:
            collector.error(
                "reserved-extension-id",
                path,
                f"Extension id '{ext_id}' is reserved by a core type or alias",
            )
        if ext.items:
            keys = list(ext.items[0].fields)
            for j, item in enumerate(ext.items):
                if "name" in item.fields:
                    collector.error(
                        "reserved-field",
                        (*path, "items", j, "fields", "name"),
                        "The field 'name' is reserved for the item name",
                    )
                if set(item.fields) != set(keys):
                    collector.error(
                        "inconsistent-fields",
                        (*path, "items", j, "fields"),
                        f"Every item must declare the same fields as the first one: "
                        f"{', '.join(keys) or 'none'}",
                    )
        for key, spec in (ext.fields or {}).items():
            spec_path: Path = (*path, "fields", key)
            if spec.vocab is not None and spec.vocab not in universe.vocab:
                collector.error(
                    "unknown-reference", (*spec_path, "vocab"), f"Unknown vocabulary '{spec.vocab}'"
                )
            if spec.place is not None and spec.place not in levels:
                collector.error(
                    "unknown-reference", (*spec_path, "place"), f"No place of level '{spec.place}'"
                )


def _check_minimum_data(universe: UniverseFile, collector: Collector) -> None:
    """Rule 10: at least one locality and one people."""
    if not any(place.level == "locality" for place in universe.places):
        collector.error("minimum-data", ("places",), "A universe needs at least one locality")
    if not universe.peoples:
        collector.error(
            "minimum-data", ("peoples",), "A universe needs at least one people with first names"
        )


# Warnings


def locale_coverage(universe: UniverseFile) -> dict[str, tuple[float, list[Path]]]:
    """Return, for each declared locale, the share of localized values it covers without a
    counted fallback, and the paths of the values it misses."""
    values = list(iter_localized(universe))
    result: dict[str, tuple[float, list[Path]]] = {}
    for locale in universe.universe.locales:
        default = universe.universe.default_locale
        missing = [path for path, value in values if not is_covered(value, locale, default)]
        ratio = 1.0 if not values else (len(values) - len(missing)) / len(values)
        result[locale] = (ratio, missing)
    return result


def _check_warnings(universe: UniverseFile, collector: Collector) -> None:
    for index, (locale, (ratio, missing)) in enumerate(locale_coverage(universe).items()):
        if missing:
            examples = ", ".join(format_path(path) for path in missing[:COVERAGE_EXAMPLES])
            more = ", ..." if len(missing) > COVERAGE_EXAMPLES else ""
            collector.warning(
                "translation-coverage",
                ("universe", "locales", index),
                f"Locale '{locale}' covers {ratio:.1%} of localized values; "
                f"{len(missing)} missing: {examples}{more}",
            )
    for index, people in enumerate(universe.peoples):
        if len(people.first_names) < MIN_FIRST_NAMES:
            collector.warning(
                "small-name-pool",
                ("peoples", index, "first_names"),
                f"People '{people.id}' has {len(people.first_names)} first names; "
                f"at least {MIN_FIRST_NAMES} are recommended",
            )
    for type_id, reason in compute_capabilities(universe).unsupported.items():
        collector.warning(
            "type-not-supported", (), f"Core type '{type_id}' is not supported: {reason}"
        )
