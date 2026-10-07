import csv
import io
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fakeverse import Fakeverse
from fakeverse.cli import app
from fakeverse.coherence import Violation
from support import FIXTURES, INVALID, MINIMAL

runner = CliRunner()
DIR = ["--universes-dir", str(FIXTURES / "universes")]


def invoke(*args: str, stdin: str | None = None) -> tuple[int, str, str]:
    result = runner.invoke(app, [*DIR, *args], input=stdin)
    return result.exit_code, result.stdout, result.stderr


def test_generate_json() -> None:
    code, out, _err = invoke("generate", "test-world", "person", "-n", "3", "--seed", "42")
    assert code == 0
    document = json.loads(out)
    assert len(document["data"]) == 3
    assert document["meta"]["seed"] == 42
    assert document["meta"]["locale"] == "en"


def test_generate_matches_python_api() -> None:
    code, out, _err = invoke(
        "generate", "test-world", "first_name", "-n", "5", "--seed", "1", "--locale", "fr_FR"
    )
    assert code == 0
    expected = Fakeverse(FIXTURES / "universes").universe("test-world", "fr-FR")
    assert json.loads(out)["data"] == expected.generate("first_name", 5, 1).items


def test_generate_ndjson_reports_drawn_seed() -> None:
    code, out, err = invoke("generate", "test-world", "relic", "-n", "2", "--format", "ndjson")
    assert code == 0
    assert len(out.splitlines()) == 2
    assert err.startswith("Seed: ")


def test_generate_csv() -> None:
    code, out, _err = invoke(
        "generate", "test-world", "address", "-n", "2", "--seed", "1", "--format", "csv"
    )
    assert code == 0
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[0] == [
        "street_address",
        "postal_code",
        "locality",
        "subdivision",
        "area",
        "formatted",
    ]
    assert len(rows) == 3


def test_generate_explain_and_options() -> None:
    code, out, _err = invoke(
        "generate",
        "test-world",
        "person",
        "--seed",
        "2",
        "--explain",
        "--unique",
        "--gender",
        "feminine",
        "--people",
        "islander",
    )
    assert code == 0
    (person,) = json.loads(out)["data"]
    assert person["gender"]["value"] == "feminine"
    assert person["people"]["value"] == "Islander"


@pytest.mark.parametrize(
    ("args", "slug"),
    [
        (["generate", "nope", "person"], "universe-not-found"),
        (["generate", "test-world", "starship"], "type-not-supported"),
        (["generate", "test-world", "person", "--locale", "de"], "locale-not-supported"),
        (["generate", "test-world", "relic", "--gender", "feminine"], "invalid-parameter"),
        (["generate", "test-world", "person", "--explain", "--format", "csv"], "invalid-parameter"),
        (
            ["generate", "test-world", "relic", "-n", "3", "--unique", "--seed", "1"],
            "pool-exhausted",
        ),
    ],
)
def test_generate_errors(args: list[str], slug: str) -> None:
    code, _out, err = invoke(*args)
    assert code == 1
    assert f"Error ({slug})" in err


def test_template_from_file_and_stdin(tmp_path: Path) -> None:
    template = {"name": "person.full_name", "town": "person.address.locality"}
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template))
    code, out, _err = invoke("template", "test-world", str(path), "-n", "4", "--seed", "3")
    assert code == 0
    from_file = json.loads(out)
    assert from_file["meta"]["type"] == "template"
    code, out, _err = invoke(
        "template", "test-world", "-", "-n", "4", "--seed", "3", stdin=json.dumps(template)
    )
    assert code == 0
    assert json.loads(out) == from_file


def test_template_csv() -> None:
    code, out, _err = invoke(
        "template",
        "test-world",
        "-",
        "--seed",
        "1",
        "--format",
        "csv",
        stdin='{"who": {"name": "person.full_name"}}',
    )
    assert code == 0
    assert out.splitlines()[0] == "who.name"


def test_template_errors(tmp_path: Path) -> None:
    code, _out, err = invoke("template", "test-world", "-", stdin='{"a": "person.nope", "b": 1}')
    assert code == 1
    assert "Error (invalid-template): Invalid template: 2 error(s)." in err
    assert "  /a: Unknown field 'nope'" in err
    code, _out, err = invoke("template", "test-world", "-", stdin="{not json")
    assert code == 1
    assert "Cannot read template" in err
    code, _out, err = invoke("template", "test-world", str(tmp_path / "missing.json"))
    assert code == 1
    code, _out, err = invoke(
        "template", "test-world", "-", "--explain", "--format", "csv", stdin='{"a": "first_name"}'
    )
    assert code == 1
    assert "Error (invalid-parameter)" in err
    code, _out, err = invoke("template", "nope", "-", stdin='{"a": "first_name"}')
    assert code == 1
    assert "Error (universe-not-found)" in err


def test_check_coherence() -> None:
    code, out, _err = invoke("check-coherence", "-n", "20")
    assert code == 0
    assert out == "test-world: OK\n"
    code, out, _err = invoke("check-coherence", "test-world", "-n", "5", "--seed", "4")
    assert code == 0
    code, _out, err = invoke("check-coherence", "nope")
    assert code == 1
    assert "Unknown universe 'nope'." in err


def test_check_coherence_reports_violations(monkeypatch: pytest.MonkeyPatch) -> None:
    violation = Violation("test-world", "en", "person", 0, "invariant 7: 'full_name' is empty")
    monkeypatch.setattr("fakeverse.cli.check_universe", lambda *args, **kwargs: [violation])
    code, out, _err = invoke("check-coherence", "-n", "3")
    assert code == 1
    assert "test-world: 1 violation(s)" in out
    assert "test-world [en] person #0: invariant 7: 'full_name' is empty" in out


def test_empty_name_format_is_rejected_by_validation(tmp_path: Path) -> None:
    # A name_format that can render empty must be rejected by validation.
    text = MINIMAL.read_text().replace(
        "    family_names: [Smith]\n", '    name_format: "{family_name}"\n'
    )
    (tmp_path / "minimal.yaml").write_text(text)
    result = runner.invoke(app, ["validate", str(tmp_path / "minimal.yaml")])
    assert result.exit_code == 1
    assert "pattern-may-be-empty" in result.stdout


def test_commands_with_invalid_or_empty_universes(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "check-coherence"])
    assert result.exit_code == 0
    assert "No universe found." in result.stderr
    shutil.copy(INVALID / "r10-no-people.yaml", tmp_path)
    result = runner.invoke(app, ["--universes-dir", str(tmp_path), "generate", "x", "person"])
    assert result.exit_code == 1
    assert "minimum-data" in result.stderr


def test_template_too_deeply_nested(tmp_path: Path) -> None:
    path = tmp_path / "deep.json"
    path.write_text('{"a":' * 200_000 + "1" + "}" * 200_000)
    result = runner.invoke(app, [*DIR, "template", "test-world", str(path)])
    # An error message rather than a traceback (3.12 and 3.13 cannot even parse it).
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "Error" in result.stderr or "Cannot read template" in result.stderr


def test_template_colocate() -> None:
    template = '{"town": "person.address.locality", "office": "organization.address.locality"}'
    code, out, _err = invoke(
        "template", "test-world", "-", "-n", "20", "--seed", "1",
        "--colocate", "person,organization", stdin=template,
    )  # fmt: skip
    assert code == 0
    assert all(row["town"] == row["office"] for row in json.loads(out)["data"])
    code, _out, err = invoke("template", "test-world", "-", "--colocate", "person", stdin=template)
    assert code == 1
    assert "A group needs at least two instances" in err


def test_uniqueness_flags() -> None:
    code, out, _err = invoke("generate", "test-world", "relic", "-n", "4", "--seed", "1")
    assert code == 0
    assert json.loads(out)["meta"]["duplicates"] == 2
    code, _out, err = invoke("generate", "test-world", "relic", "-n", "4", "--unique")
    assert code == 1
    assert "Error (pool-exhausted)" in err
    code, out, _err = invoke("generate", "test-world", "relic", "-n", "4", "--no-unique")
    assert code == 0
