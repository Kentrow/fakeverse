"""Build the data snapshots served by the API.

For every release of ``releases.toml`` made with the current engine revision, extract
``universes/*.yaml`` from the git tag ``v<version>`` into ``<output>/<version>/``; add the data
of the working tree for the current package version, and copy ``releases.toml``. The API then
runs with ``FAKEVERSE_DATA_DIR=<output>``.

    python scripts/build_snapshots.py --output data [--repo .]

Standard library only, so that it runs in the build stage of the Docker image.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path


def read_constant(path: Path, pattern: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise SystemExit(f"Cannot read {pattern!r} in {path}")
    return match[1]


def engine_revision(repo: Path) -> int:
    path = repo / "src" / "fakeverse" / "engine" / "revision.py"
    return int(read_constant(path, r"^ENGINE_REVISION: Final\[int\] = (\d+)$"))


def package_version(repo: Path) -> str:
    return read_constant(repo / "src" / "fakeverse" / "__init__.py", r'^__version__ = "([^"]+)"$')


def releases(repo: Path) -> list[dict[str, object]]:
    path = repo / "releases.toml"
    if not path.is_file():
        return []
    entries: list[dict[str, object]] = tomllib.loads(path.read_text(encoding="utf-8")).get(
        "releases", []
    )
    return entries


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout


def extract_release(repo: Path, version: str, target: Path) -> int:
    """Copy the universe files of tag ``v<version>`` into ``target``; return their count."""
    tag = f"v{version}"
    names = [
        name
        for name in git(repo, "ls-tree", "--name-only", f"{tag}:universes").splitlines()
        if name.endswith(".yaml")
    ]
    target.mkdir(parents=True)
    for name in names:
        content = subprocess.run(
            ["git", "-C", str(repo), "show", f"{tag}:universes/{name}"],
            check=True,
            capture_output=True,
        ).stdout
        (target / name).write_bytes(content)
    return len(names)


def build(repo: Path, output: Path) -> list[str]:
    """Build every snapshot; return the versions built, oldest first."""
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    revision = engine_revision(repo)
    current = package_version(repo)
    built: list[str] = []
    for entry in releases(repo):
        version = str(entry["version"])
        if int(str(entry["engine_revision"])) != revision or version == current:
            continue
        count = extract_release(repo, version, output / version)
        print(f"{version}: {count} universe(s) from tag v{version}")
        built.append(version)
    target = output / current
    target.mkdir()
    files = sorted((repo / "universes").glob("*.yaml"))
    for path in files:
        shutil.copy(path, target / path.name)
    print(f"{current}: {len(files)} universe(s) from the working tree")
    built.append(current)
    if (repo / "releases.toml").is_file():
        shutil.copy(repo / "releases.toml", output / "releases.toml")
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True, help="Snapshot directory.")
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root.")
    args = parser.parse_args(argv)
    try:
        build(args.repo.resolve(), args.output)
    except subprocess.CalledProcessError as error:
        print(f"git failed: {error.stderr}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
