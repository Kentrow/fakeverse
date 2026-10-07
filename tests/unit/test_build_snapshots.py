"""scripts/build_snapshots.py, on a throwaway git repository."""

import importlib.util
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

from fakeverse import __version__
from fakeverse.api.snapshots import SnapshotStore
from fakeverse.engine.revision import ENGINE_REVISION
from support import MINIMAL, TEST_WORLD

ROOT = Path(__file__).parents[2]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "build_snapshots", ROOT / "scripts" / "build_snapshots.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=T", "-c", "user.email=t@example.org", *args],
        check=True,
        capture_output=True,
    )


def write_repo(repo: Path, version: str, revision: int, releases: str) -> None:
    (repo / "src" / "fakeverse" / "engine").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "fakeverse" / "__init__.py").write_text(f'__version__ = "{version}"\n')
    (repo / "src" / "fakeverse" / "engine" / "revision.py").write_text(
        f"ENGINE_REVISION: Final[int] = {revision}\n"
    )
    (repo / "releases.toml").write_text(releases)


RELEASE = '[[releases]]\nversion = "{v}"\nengine_revision = {r}\ndate = 2026-01-01\n\n'


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "universes").mkdir(parents=True)
    git(repo, "init", "-q")
    # 0.9.0, engine revision 0: retired.
    shutil.copy(MINIMAL, repo / "universes")
    write_repo(repo, "0.9.0", 0, RELEASE.format(v="0.9.0", r=0))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "0.9.0")
    git(repo, "tag", "v0.9.0")
    # 1.0.0, engine revision 1, with minimal only.
    write_repo(repo, "1.0.0", 1, RELEASE.format(v="0.9.0", r=0) + RELEASE.format(v="1.0.0", r=1))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "1.0.0")
    git(repo, "tag", "v1.0.0")
    # Working tree: 1.1.0 in progress, with test-world added.
    shutil.copy(TEST_WORLD, repo / "universes")
    write_repo(repo, "1.1.0", 1, RELEASE.format(v="0.9.0", r=0) + RELEASE.format(v="1.0.0", r=1))
    return repo


def test_build(repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    script = load_script()
    output = tmp_path / "data"
    assert script.main(["--repo", str(repo), "--output", str(output)]) == 0
    assert sorted(p.name for p in output.iterdir()) == ["1.0.0", "1.1.0", "releases.toml"]
    assert [p.name for p in (output / "1.0.0").iterdir()] == ["minimal.yaml"]
    assert sorted(p.name for p in (output / "1.1.0").iterdir()) == [
        "minimal.yaml",
        "test-world.yaml",
    ]
    assert "1.0.0: 1 universe(s) from tag v1.0.0" in capsys.readouterr().out
    store = SnapshotStore.load(output, [])
    assert store.versions == ["1.0.0", "1.1.0"]
    assert store.retired == {"0.9.0": 0}


def test_rebuild_replaces_the_output(repo: Path, tmp_path: Path) -> None:
    script = load_script()
    output = tmp_path / "data"
    (output / "stale").mkdir(parents=True)
    script.build(repo, output)
    assert not (output / "stale").exists()


def test_released_version_equal_to_the_package_uses_the_working_tree(
    repo: Path, tmp_path: Path
) -> None:
    script = load_script()
    write_repo(repo, "1.0.0", 1, RELEASE.format(v="1.0.0", r=1))
    assert script.build(repo, tmp_path / "data") == ["1.0.0"]
    assert (tmp_path / "data" / "1.0.0" / "test-world.yaml").exists()


def test_missing_tag_fails(repo: Path, tmp_path: Path) -> None:
    script = load_script()
    write_repo(repo, "1.1.0", 1, RELEASE.format(v="1.0.5", r=1))
    assert script.main(["--repo", str(repo), "--output", str(tmp_path / "data")]) == 1


def test_without_releases_file(repo: Path, tmp_path: Path) -> None:
    script = load_script()
    (repo / "releases.toml").unlink()
    assert script.build(repo, tmp_path / "data") == ["1.1.0"]
    assert not (tmp_path / "data" / "releases.toml").exists()


def test_unreadable_constant(tmp_path: Path) -> None:
    script = load_script()
    (tmp_path / "f.py").write_text("nothing\n")
    with pytest.raises(SystemExit, match="Cannot read"):
        script.read_constant(tmp_path / "f.py", r"^X = (\d+)$")


def test_reads_the_real_repository() -> None:
    script = load_script()
    assert script.package_version(ROOT) == __version__
    assert script.engine_revision(ROOT) == ENGINE_REVISION
