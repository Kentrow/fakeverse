"""scripts/check_commits.py: Conventional Commits and sign-off."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[2]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_commits", ROOT / "scripts" / "check_commits.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = load_script()
SIGNED = "\n\nSigned-off-by: Ada <ada@example.com>\n"


@pytest.mark.parametrize(
    "header",
    [
        "feat: add a universe",
        "fix(universes): correct a French name",
        "feat(api)!: rename a parameter",
        "chore(release): 0.2.0",
        "docs: explain v1.2",
    ],
)
def test_valid_headers(header: str) -> None:
    assert check.header_problems(header) == []
    assert check.message_problems(header + SIGNED) == []


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("Add a universe", "does not follow Conventional Commits"),
        ("feature: add a universe", "does not follow Conventional Commits"),
        ("feat:add a universe", "does not follow Conventional Commits"),
        ("feat(API): add", "does not follow Conventional Commits"),
        ("feat: ", "does not follow Conventional Commits"),
        ("feat: add a universe.", "ends with a period"),
        ("feat: " + "x" * 95, "longer than 100 characters"),
    ],
)
def test_invalid_headers(header: str, problem: str) -> None:
    problems = check.header_problems(header)
    assert len(problems) == 1
    assert problem in problems[0]


def test_messages() -> None:
    assert check.message_problems("") == ["The commit message is empty"]
    assert check.message_problems("feat: x\n") == [
        "'feat: x' is not signed off: commit with 'git commit -s'"
    ]
    assert check.message_problems("feat: x\nbody" + SIGNED) == [
        "'feat: x' must be followed by a blank line"
    ]
    commented = "\n# Please enter the commit message\nfeat: x" + SIGNED + "# comment\n"
    assert check.message_problems(commented) == []


def test_local_messages_tolerate_merges_and_autosquash() -> None:
    for header in ("Merge branch 'main'", "fixup! feat: x", "squash! feat: x", "amend! feat: x"):
        assert check.message_problems(header, local=True) == []
        assert check.message_problems(header) != []


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_range(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Ada")
    git(tmp_path, "config", "user.email", "ada@example.com")
    for message in ("chore: base", "feat: good", "bad commit"):
        git(tmp_path, "commit", "-q", "--allow-empty", "-s", "-m", message)
    git(tmp_path, "commit", "-q", "--allow-empty", "-m", "fix: unsigned")
    bot = ("-c", "user.name=dependabot[bot]", "-c", "user.email=bot@example.com")
    git(tmp_path, *bot, "commit", "-q", "--allow-empty", "-m", "build(deps): bump x")
    assert check.range_problems("HEAD~4..HEAD", tmp_path) == [
        "'fix: unsigned' is not signed off: commit with 'git commit -s'",
        "'bad commit' does not follow Conventional Commits: 'type(scope): description' with a "
        "type among build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test",
    ]


def test_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("feat: x" + SIGNED)
    assert check.main(["--message-file", str(message)]) == 0
    assert check.main(["--title", "feat: x"]) == 0
    assert check.main(["--title", "Update README.md"]) == 1
    assert "CONTRIBUTING.md" in capsys.readouterr().out
    git(tmp_path, "init", "-q", "-b", "main")
    git(
        tmp_path,
        "-c",
        "user.name=Ada",
        "-c",
        "user.email=ada@example.com",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "feat: x" + SIGNED,
    )
    monkeypatch.chdir(tmp_path)
    assert check.main(["--range", "HEAD"]) == 0
