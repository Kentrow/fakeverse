"""Loading of universe files from disk.

YAML is read with the safe loader only, in its libyaml version when available. The file is
composed once into a node tree, which gives the line of every YAML path and reveals duplicate
keys (silently merged by a plain load), then the data is constructed from that tree.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Final

import yaml

from fakeverse.errors import UniverseValidationError
from fakeverse.model import UniverseFile
from fakeverse.validation import Collector, Issue, validate_data
from fakeverse.validation import Path as YamlPath

MAX_FILE_SIZE: Final[int] = 2 * 1024 * 1024
SafeLoader: Final = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
"""The safe loader of libyaml, about ten times faster, or the pure Python one."""
UNIVERSE_SUFFIX: Final[str] = ".yaml"


@dataclass(slots=True)
class LoadResult:
    """Outcome of loading one universe file."""

    path: Path
    universe: UniverseFile | None
    """The universe, or None when the file has errors."""
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    def is_valid(self, *, strict: bool = False) -> bool:
        """Whether the file has no error (and no warning when ``strict``)."""
        return not self.errors and not (strict and self.warnings)


class LineIndex:
    """Lines of the values of a YAML document, by path."""

    def __init__(self) -> None:
        self.lines: dict[YamlPath, int] = {}

    def line_of(self, path: YamlPath) -> int | None:
        """Return the line of ``path``, or of its nearest known ancestor."""
        for end in range(len(path), -1, -1):
            line = self.lines.get(path[:end])
            if line is not None:
                return line
        return None


def _index_node(node: yaml.Node, path: YamlPath, index: LineIndex, collector: Collector) -> None:
    index.lines.setdefault(path, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        seen: list[str] = []
        for key_node, value_node in node.value:
            key = str(key_node.value)
            if key in seen:
                collector.issues.append(
                    Issue(
                        "error",
                        "duplicate-key",
                        f"Duplicate key '{key}'",
                        (*path, key),
                        key_node.start_mark.line + 1,
                    )
                )
                continue
            seen.append(key)
            index.lines[(*path, key)] = key_node.start_mark.line + 1
            _index_node(value_node, (*path, key), index, collector)
    elif isinstance(node, yaml.SequenceNode):
        for position, item in enumerate(node.value):
            _index_node(item, (*path, position), index, collector)


def load_file(path: Path) -> LoadResult:
    """Read and validate one universe file. Never raises on invalid content."""
    result = LoadResult(path=path, universe=None)
    index = LineIndex()
    collector = Collector(index.line_of)
    parsed = _parse(path, index, collector)
    if isinstance(parsed, Issue):
        result.issues.append(parsed)
        return _with_file(result)
    try:
        universe, issues = validate_data(parsed, expected_id=path.stem, line_of=index.line_of)
    except RecursionError:
        result.issues.append(_NESTED)
        return _with_file(result)
    result.issues = [*collector.issues, *issues]
    result.universe = universe if not collector.has_errors else None
    return _with_file(result)


_NESTED = Issue("error", "yaml-syntax", "Invalid YAML: nested too deeply")


def _parse(path: Path, index: LineIndex, collector: Collector) -> object:
    """Parse a file and index its lines; return the data, or the issue that prevents it."""
    size = path.stat().st_size
    if size >= MAX_FILE_SIZE:
        return Issue("error", "file-too-large", f"File of {size} bytes; the limit is 2 MB")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return Issue("error", "yaml-syntax", f"Invalid UTF-8 encoding: {exc.reason}")
    try:
        alias = _first_alias(text)
        if alias is not None:
            message = "YAML anchors and aliases are not allowed in universe files"
            return Issue("error", "yaml-alias", message, (), alias)
        loader = SafeLoader(text)
        try:
            node = loader.get_single_node()
            data: object = None
            if node is not None:
                _index_node(node, (), index, collector)
                data = loader.construct_document(node)
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = mark.line + 1 if mark is not None else None
        problem = getattr(exc, "problem", None) or str(exc)
        return Issue("error", "yaml-syntax", f"Invalid YAML: {problem}", (), line)
    except RecursionError:
        return _NESTED
    return data


def _first_alias(text: str) -> int | None:
    """Line of the first YAML anchor or alias, if any.

    Universe files never need them, and aliases can expand exponentially.
    """
    for token in yaml.scan(text, Loader=SafeLoader):
        if isinstance(token, yaml.AnchorToken | yaml.AliasToken):
            line: int = token.start_mark.line + 1
            return line
    return None


def _with_file(result: LoadResult) -> LoadResult:
    name = str(result.path)
    result.issues = [
        Issue(i.severity, i.code, i.message, i.path, i.line, name) for i in result.issues
    ]
    return result


def find_universe_files(paths: Iterable[Path]) -> list[Path]:
    """Expand directories into their ``*.yaml`` files, sorted by name."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.glob(f"*{UNIVERSE_SUFFIX}")))
        else:
            found.append(path)
    return found


def load_directory(directory: Path) -> dict[str, UniverseFile]:
    """Load and validate every universe of a directory, keyed by id in file name order.

    Raises:
        UniverseValidationError: with the complete list of issues if any file is invalid.
    """
    results = [load_file(path) for path in find_universe_files([directory])]
    if any(result.errors for result in results):
        raise UniverseValidationError([issue for result in results for issue in result.issues])
    return {
        result.universe.universe.id: result.universe
        for result in results
        if result.universe is not None
    }


def embedded_universes_dir() -> Path:
    """Return the directory of the universes shipped with the package.

    In a wheel the universes live in ``fakeverse/_universes``. In a source checkout (editable
    install) they are read from the ``universes/`` directory of the repository.
    """
    packaged = files("fakeverse").joinpath("_universes")
    if isinstance(packaged, Path) and packaged.is_dir():
        return packaged
    return Path(__file__).resolve().parents[2] / "universes"
