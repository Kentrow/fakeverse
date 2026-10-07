import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from fakeverse import __version__
from fakeverse.cli import app
from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.model import universe_json_schema
from support import INVALID, MINIMAL, TEST_WORLD

runner = CliRunner()


def test_validate_valid_file() -> None:
    result = runner.invoke(app, ["validate", str(MINIMAL)])
    assert result.exit_code == 0, result.output
    assert "minimal.yaml: valid (0 error(s), 0 warning(s))" in result.output
    assert "1 file(s) checked, 0 invalid." in result.output


def test_validate_invalid_file_exits_1() -> None:
    result = runner.invoke(app, ["validate", str(MINIMAL), str(INVALID / "r03-duplicate-id.yaml")])
    assert result.exit_code == 1
    assert "error: line 36: organizations[1].id: Duplicate id 'guild'" in result.output
    assert "2 file(s) checked, 1 invalid." in result.output


def test_validate_strict_turns_warnings_into_errors() -> None:
    assert runner.invoke(app, ["validate", str(TEST_WORLD)]).exit_code == 0
    result = runner.invoke(app, ["validate", "--strict", str(TEST_WORLD)])
    assert result.exit_code == 1
    assert "invalid (0 error(s), 3 warning(s))" in result.output


def test_validate_json() -> None:
    result = runner.invoke(app, ["validate", "--json", str(INVALID / "r10-no-people.yaml")])
    assert result.exit_code == 1
    report = json.loads(result.stdout)
    assert report["valid"] is False
    (entry,) = report["files"]
    assert entry["universe"] is None
    assert entry["errors"] == 1
    assert entry["issues"][0]["code"] == "minimum-data"


def test_validate_defaults_to_universes_dir(tmp_path: Path) -> None:
    shutil.copy(MINIMAL, tmp_path)
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "validate"])
    assert result.exit_code == 0
    assert "minimal.yaml: valid" in result.output


def test_validate_empty_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(tmp_path)])
    assert result.exit_code == 0
    assert "No universe file found." in result.output


def test_coverage_text(tmp_path: Path) -> None:
    shutil.copy(TEST_WORLD, tmp_path)
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage"])
    assert result.exit_code == 0, result.output
    assert "test-world - Test World" in result.output
    assert "fr           95.2% (4 missing)" in result.output
    assert "      - places[4].name" in result.output
    assert "Extension: relic (name, kind, age)" in result.output


def test_coverage_json_and_filter(tmp_path: Path) -> None:
    shutil.copy(TEST_WORLD, tmp_path)
    shutil.copy(MINIMAL, tmp_path)
    shutil.copy(MINIMAL, tmp_path / "other.yaml")
    (tmp_path / "other.yaml").write_text(
        MINIMAL.read_text()
        .replace("id: minimal", "id: other")
        .replace('  email: "{first_name|slug}@example.org"\n', "")
    )
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage", "other", "--json"])
    assert result.exit_code == 0, result.output
    (report,) = json.loads(result.stdout)
    assert report["id"] == "other"
    assert report["locale_coverage"]["fr"] == {"ratio": 1.0, "missing": []}
    assert report["capabilities"]["unsupported"] == {"email": "no 'email' pattern"}
    text = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage", "other"])
    assert "Not supported: email (no 'email' pattern)" in text.output


def test_coverage_unknown_universe(tmp_path: Path) -> None:
    shutil.copy(MINIMAL, tmp_path)
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage", "nope"])
    assert result.exit_code == 1
    assert "Unknown universe 'nope'." in result.output


def test_coverage_invalid_universe(tmp_path: Path) -> None:
    shutil.copy(INVALID / "r10-no-people.yaml", tmp_path)
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage"])
    assert result.exit_code == 1
    assert "minimum-data" in result.output


def test_coverage_empty_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "coverage"])
    assert result.exit_code == 0
    assert "No universe found." in result.output


def test_schema_export() -> None:
    result = runner.invoke(app, ["schema", "export"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == universe_json_schema()


def test_info() -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert result.output.splitlines() == [
        f"fakeverse {__version__}",
        f"Engine revision: {ENGINE_REVISION}",
        "Embedded universes: lotr, starwars",
    ]
