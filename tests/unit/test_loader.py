import shutil
from pathlib import Path

import pytest

from fakeverse.errors import FakeverseError, UniverseValidationError
from fakeverse.loader import (
    embedded_universes_dir,
    find_universe_files,
    load_directory,
    load_file,
)
from support import INVALID, MINIMAL, TEST_WORLD


def test_load_directory(tmp_path: Path) -> None:
    shutil.copy(TEST_WORLD, tmp_path)
    shutil.copy(MINIMAL, tmp_path)
    universes = load_directory(tmp_path)
    assert list(universes) == ["minimal", "test-world"]


def test_load_directory_reports_every_issue(tmp_path: Path) -> None:
    shutil.copy(MINIMAL, tmp_path)
    shutil.copy(INVALID / "r04-unknown-parent.yaml", tmp_path)
    shutil.copy(INVALID / "r10-no-people.yaml", tmp_path)
    with pytest.raises(UniverseValidationError) as info:
        load_directory(tmp_path)
    error = info.value
    assert isinstance(error, FakeverseError)
    assert error.slug == "universe-validation-error"
    assert {issue.code for issue in error.issues} == {"unknown-reference", "minimum-data"}
    assert "2 error(s)" in str(error)
    assert "r04-unknown-parent.yaml:23: places[2].parent" in str(error)


def test_find_universe_files(tmp_path: Path) -> None:
    (tmp_path / "b.yaml").write_text("")
    (tmp_path / "a.yaml").write_text("")
    (tmp_path / "notes.txt").write_text("")
    explicit = tmp_path / "notes.txt"
    assert find_universe_files([tmp_path, explicit]) == [
        tmp_path / "a.yaml",
        tmp_path / "b.yaml",
        explicit,
    ]


def test_empty_file_is_a_schema_error(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("")
    assert [issue.code for issue in load_file(path).errors] == ["schema"]


def test_yaml_syntax_error_has_a_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.yaml"
    path.write_text("format: 1\nuniverse: [\n")
    (issue,) = load_file(path).errors
    assert issue.code == "yaml-syntax"
    assert issue.line == 3


def test_issue_formatting() -> None:
    (issue,) = load_file(INVALID / "r04-unknown-parent.yaml").errors
    assert issue.format(with_file=False) == (
        "line 23: places[2].parent: Unknown place 'nowhere' [unknown-reference]"
    )
    assert issue.to_dict() == {
        "severity": "error",
        "code": "unknown-reference",
        "message": "Unknown place 'nowhere'",
        "path": "places[2].parent",
        "line": 23,
    }


def test_embedded_universes_dir_in_a_source_checkout() -> None:
    directory = embedded_universes_dir()
    assert directory == Path(__file__).parents[2] / "universes"
    assert (directory / "LICENSE").is_file()


def test_invalid_encoding(tmp_path: Path) -> None:
    path = tmp_path / "latin.yaml"
    path.write_bytes(b"format: 1\nname: caf\xe9\n")
    (issue,) = load_file(path).errors
    assert issue.code == "yaml-syntax"
    assert "UTF-8" in issue.message


def test_recursive_alias_is_refused_quickly(tmp_path: Path) -> None:
    path = tmp_path / "recursive.yaml"
    path.write_text("a: &a [*a]\n")
    assert [issue.code for issue in load_file(path).errors] == ["yaml-alias"]


def test_deep_nesting(tmp_path: Path) -> None:
    path = tmp_path / "deep.yaml"
    path.write_text("[" * 5000 + "]" * 5000)
    assert [issue.code for issue in load_file(path).errors] == ["yaml-syntax"]
