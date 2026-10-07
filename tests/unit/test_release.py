"""scripts/release.py: version proposal, release preparation and tag check."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from fakeverse import ENGINE_REVISION, __version__

ROOT = Path(__file__).parents[2]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release", ROOT / "scripts" / "release.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


release = load_script()

CHANGELOG = """# Changelog

## [Unreleased]

### Added

- Something new.

[Unreleased]: https://github.com/owner/repo/commits/main
"""


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def commit(repo: Path, message: str, path: str = "notes.txt") -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(file.read_text() + "x\n" if file.exists() else "x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src" / "fakeverse" / "engine").mkdir(parents=True)
    (tmp_path / "src" / "fakeverse" / "__init__.py").write_text('__version__ = "0.1.0"\n')
    (tmp_path / "src" / "fakeverse" / "engine" / "revision.py").write_text(
        "ENGINE_REVISION: Final[int] = 1\n"
    )
    (tmp_path / "releases.toml").write_text("# Release history.\n")
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[project.urls]\nRepository = "https://github.com/owner/repo"\n'
    )
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "user.email", "test@example.com")
    commit(tmp_path, "feat: initial")
    return tmp_path


def released(repo: Path) -> None:
    """Prepare and tag the first release, then open a new [Unreleased] section."""
    release.prepare(repo, None, "2026-10-10")
    commit(repo, "chore(release): 0.1.0")
    git(repo, "tag", "v0.1.0")
    changelog = (repo / "CHANGELOG.md").read_text()
    (repo / "CHANGELOG.md").write_text(
        changelog.replace("## [Unreleased]\n", "## [Unreleased]\n\n- Next change.\n", 1)
    )


def test_first_release(repo: Path) -> None:
    summary = release.prepare(repo, None, "2026-10-10")
    assert summary.startswith("Release 0.1.0 (first release; proposed: 0.1.0), dated 2026-10-10.")
    assert "git tag -a v0.1.0" in summary
    changelog = (repo / "CHANGELOG.md").read_text()
    assert "## [Unreleased]\n\n## [0.1.0] - 2026-10-10\n\n### Added" in changelog
    assert changelog.endswith(
        "[Unreleased]: https://github.com/owner/repo/compare/v0.1.0...HEAD\n"
        "[0.1.0]: https://github.com/owner/repo/releases/tag/v0.1.0\n"
    )
    assert (repo / "releases.toml").read_text() == (
        '# Release history.\n\n[[releases]]\nversion = "0.1.0"\nengine_revision = 1\n'
        "date = 2026-10-10\n"
    )
    assert release.check(repo, "v0.1.0") == []


@pytest.mark.parametrize(
    ("message", "path", "expected"),
    [
        ("fix: a bug", "src/x.py", "0.1.1"),
        ("feat: a feature", "src/x.py", "0.2.0"),
        ("fix(universes): a name", "universes/lotr.yaml", "0.2.0"),
        ("feat!: a breaking change", "src/x.py", "0.2.0"),
        ("refactor: x\n\nBREAKING CHANGE: y", "src/x.py", "0.2.0"),
    ],
)
def test_next_version_before_1_0(repo: Path, message: str, path: str, expected: str) -> None:
    released(repo)
    commit(repo, message, path)
    release.prepare(repo, None, "2026-10-11")
    assert f'__version__ = "{expected}"' in (repo / "src/fakeverse/__init__.py").read_text()
    changelog = (repo / "CHANGELOG.md").read_text()
    assert f"## [{expected}] - 2026-10-11\n\n- Next change." in changelog
    assert f"[{expected}]: https://github.com/owner/repo/compare/v0.1.0...v{expected}" in changelog
    assert release.check(repo, f"v{expected}") == []


def changes(**kwargs: object) -> object:
    return release.Changes(commits=1, **kwargs)


def test_next_version_from_1_0() -> None:
    assert release.next_version("1.2.3", changes()) == ("1.2.4", "PATCH: fixes only")
    assert release.next_version("1.2.3", changes(features=["feat: x"])) == (
        "1.3.0",
        "MINOR: new features",
    )
    assert release.next_version("1.2.3", changes(data=True)) == (
        "1.3.0",
        "MINOR: universe data changed",
    )
    assert release.next_version("1.2.3", changes(breaking=["feat!: x"])) == (
        "2.0.0",
        "MAJOR: breaking changes",
    )
    assert release.next_version("1.2.3", changes(revision=True)) == (
        "2.0.0",
        "MAJOR: ENGINE_REVISION changed",
    )


def test_engine_revision_change_must_be_noted(repo: Path) -> None:
    released(repo)
    (repo / "src/fakeverse/engine/revision.py").write_text("ENGINE_REVISION: Final[int] = 2\n")
    commit(repo, "fix: change the output")
    with pytest.raises(release.ReleaseError, match="ENGINE_REVISION changed"):
        release.prepare(repo, None, "2026-10-11")
    changelog = (repo / "CHANGELOG.md").read_text()
    (repo / "CHANGELOG.md").write_text(
        changelog.replace("- Next change.", "- `ENGINE_REVISION` = 2.", 1)
    )
    assert release.prepare(repo, None, "2026-10-11").startswith(
        "Release 0.2.0 (MINOR: ENGINE_REVISION changed"
    )


def test_prepare_refusals(repo: Path) -> None:
    released(repo)
    with pytest.raises(release.ReleaseError, match="Nothing to release"):
        release.prepare(repo, None, "2026-10-11")
    commit(repo, "fix: x")
    with pytest.raises(release.ReleaseError, match="does not follow"):
        release.prepare(repo, "0.1.0", "2026-10-11")
    with pytest.raises(release.ReleaseError, match="Invalid version"):
        release.prepare(repo, "1.0", "2026-10-11")
    with pytest.raises(ValueError, match="isoformat"):
        release.prepare(repo, None, "October 11")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n\n## [0.1.0] - x\n")
    with pytest.raises(release.ReleaseError, match="empty"):
        release.prepare(repo, None, "2026-10-11")
    (repo / "CHANGELOG.md").write_text("# Changelog\n")
    with pytest.raises(release.ReleaseError, match="no '## \\[Unreleased\\]' section"):
        release.prepare(repo, None, "2026-10-11")


def test_prepare_without_tag(repo: Path) -> None:
    (repo / "releases.toml").write_text(
        '[[releases]]\nversion = "0.1.0"\nengine_revision = 1\ndate = 2026-10-10\n'
    )
    with pytest.raises(release.ReleaseError, match=r"Cannot compare with tag v0\.1\.0"):
        release.prepare(repo, None, "2026-10-11")


def test_dry_run_changes_nothing(repo: Path) -> None:
    before = {p: p.read_text() for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts}
    summary = release.prepare(repo, "0.1.0", "2026-10-10", dry_run=True)
    assert "Next steps" not in summary
    assert {p: p.read_text() for p in before} == before


def test_check_problems(repo: Path) -> None:
    released(repo)
    assert release.check(repo, "v0.1.1") == ["Tag v0.1.1 does not match the package version 0.1.0"]
    (repo / "CHANGELOG.md").write_text("# Changelog\n")
    assert release.check(repo, "v0.1.0") == [
        "CHANGELOG.md has no '## [0.1.0] - 2026-10-10' section"
    ]
    (repo / "releases.toml").write_text(
        '[[releases]]\nversion = "0.1.0"\nengine_revision = 2\ndate = 2026-10-10\n'
    )
    assert release.check(repo, "v0.1.0")[0] == (
        "releases.toml lists 0.1.0 with engine revision 2, but ENGINE_REVISION is 1"
    )
    (repo / "releases.toml").unlink()
    assert release.check(repo, "v0.1.0") == ["releases.toml has no entry for 0.1.0"]
    (repo / "src/fakeverse/__init__.py").write_text("")
    assert release.check(repo, "v0.1.0") == ["Cannot read the package version"]


def test_main(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert release.main(["--repo", str(repo), "prepare", "--dry-run", "--date", "2026-10-10"]) == 0
    assert "Release 0.1.0" in capsys.readouterr().out
    assert release.main(["--repo", str(repo), "check", "v0.1.0"]) == 1
    assert "releases.toml has no entry for 0.1.0" in capsys.readouterr().out
    assert release.main(["--repo", str(repo), "prepare", "--version", "x"]) == 1
    released(repo)
    assert release.main(["--repo", str(repo), "check", "v0.1.0"]) == 0
    assert "v0.1.0: OK" in capsys.readouterr().out


def test_real_repository() -> None:
    entries = release.read_releases(ROOT)
    if any(str(entry["version"]) == __version__ for entry in entries):
        assert release.check(ROOT, f"v{__version__}") == []
    else:
        # Before the first release: everything is in the [Unreleased] section.
        assert not entries
        changelog = (ROOT / "CHANGELOG.md").read_text()
        assert f"`ENGINE_REVISION` = {ENGINE_REVISION}" in release.unreleased_notes(changelog)


def test_notes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    released(repo)
    assert release.main(["--repo", str(repo), "notes", "0.1.0"]) == 0
    assert capsys.readouterr().out == "### Added\n\n- Something new.\n"
    assert release.main(["--repo", str(repo), "notes", "9.9.9"]) == 1
    assert "no '## [9.9.9] - ' section" in capsys.readouterr().out
