"""Prepare and check releases, following the versioning policy of CONTRIBUTING.md.

    python scripts/release.py prepare [--version X.Y.Z] [--date YYYY-MM-DD] [--dry-run]
    python scripts/release.py check vX.Y.Z
    python scripts/release.py notes X.Y.Z

``prepare`` proposes the next version from the changes since the last release (Conventional
Commits, universe data and ``ENGINE_REVISION``), then dates the ``[Unreleased]`` section of
CHANGELOG.md, sets the package version and appends the release to releases.toml. ``check``,
run by the release workflow, verifies that a tag matches them, and ``notes`` prints the
changelog section of a version, for the GitHub release.

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

VERSION_FILE: Final = Path("src/fakeverse/__init__.py")
REVISION_FILE: Final = Path("src/fakeverse/engine/revision.py")
VERSION_PATTERN: Final = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
REVISION_PATTERN: Final = re.compile(r"^ENGINE_REVISION: Final\[int\] = (\d+)$", re.MULTILINE)
SEMVER: Final = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
HEADER: Final = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?(?P<breaking>!)?: ")
UNRELEASED: Final = "## [Unreleased]"
PATCH, MINOR, MAJOR = 0, 1, 2


class ReleaseError(Exception):
    """A problem that prevents the release."""


def read_version(repo: Path) -> str:
    match = VERSION_PATTERN.search((repo / VERSION_FILE).read_text(encoding="utf-8"))
    if match is None:
        raise ReleaseError("Cannot read the package version")
    return match[1]


def read_revision(repo: Path) -> int:
    match = REVISION_PATTERN.search((repo / REVISION_FILE).read_text(encoding="utf-8"))
    if match is None:
        raise ReleaseError("Cannot read ENGINE_REVISION")
    return int(match[1])


def read_releases(repo: Path) -> list[dict[str, object]]:
    path = repo / "releases.toml"
    if not path.is_file():
        return []
    entries: list[dict[str, object]] = tomllib.loads(path.read_text(encoding="utf-8")).get(
        "releases", []
    )
    return entries


def parse_version(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version)
    if match is None:
        raise ReleaseError(f"Invalid version {version!r}: expected MAJOR.MINOR.PATCH")
    return int(match[1]), int(match[2]), int(match[3])


def repository_url(repo: Path) -> str:
    project = tomllib.loads((repo / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return str(project["urls"]["Repository"]).rstrip("/")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout


@dataclass
class Changes:
    """What changed since the last release, as far as versioning is concerned."""

    commits: int = 0
    breaking: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    data: bool = False
    revision: bool = False


def collect_changes(repo: Path, last: dict[str, object]) -> Changes:
    """Changes between the tag of the last release and HEAD."""
    tag = f"v{last['version']}"
    try:
        log = git(repo, "log", "--no-merges", "--format=%B%x1e", f"{tag}..HEAD")
        data = git(repo, "diff", "--name-only", tag, "HEAD", "--", "universes/")
    except subprocess.CalledProcessError as error:
        raise ReleaseError(f"Cannot compare with tag {tag}: {error.stderr.strip()}") from error
    changes = Changes(data=bool(data.strip()))
    changes.revision = read_revision(repo) != int(str(last["engine_revision"]))
    for message in filter(None, (entry.strip() for entry in log.split("\x1e"))):
        changes.commits += 1
        header, *body = message.splitlines()
        match = HEADER.match(header)
        if (match is not None and match["breaking"]) or any(
            line.startswith(("BREAKING CHANGE:", "BREAKING-CHANGE:")) for line in body
        ):
            changes.breaking.append(header)
        elif match is not None and match["type"] == "feat":
            changes.features.append(header)
    return changes


def next_version(last: str, changes: Changes) -> tuple[str, str]:
    """The version that follows ``last`` given ``changes``, and the reason."""
    major, minor, patch = parse_version(last)
    if changes.breaking or changes.revision:
        level, reason = MAJOR, "breaking changes" if changes.breaking else "ENGINE_REVISION changed"
    elif changes.features or changes.data:
        level, reason = MINOR, "new features" if changes.features else "universe data changed"
    else:
        level, reason = PATCH, "fixes only"
    if major == 0:
        # Before 1.0.0, a breaking change only bumps the minor version.
        level = min(level, MINOR)
    if level == MAJOR:
        return f"{major + 1}.0.0", f"MAJOR: {reason}"
    if level == MINOR:
        return f"{major}.{minor + 1}.0", f"MINOR: {reason}"
    return f"{major}.{minor}.{patch + 1}", f"PATCH: {reason}"


def unreleased_notes(changelog: str) -> str:
    """Content of the ``[Unreleased]`` section."""
    return section(changelog, UNRELEASED)


def section(changelog: str, heading: str) -> str:
    """Content of the changelog section that starts with ``heading``."""
    start = changelog.find(heading)
    if start < 0:
        raise ReleaseError(f"CHANGELOG.md has no '{heading}' section")
    body = changelog[start + len(heading) :]
    body = body[body.find("\n") + 1 :] if "\n" in body else ""
    end = min(
        (i for i in (body.find("\n## ["), body.find("\n[Unreleased]:")) if i >= 0),
        default=len(body),
    )
    return body[:end].strip()


def date_changelog(changelog: str, version: str, date: str, previous: str | None, url: str) -> str:
    """Turn ``[Unreleased]`` into the section of ``version`` and update the links."""
    changelog = changelog.replace(UNRELEASED, f"{UNRELEASED}\n\n## [{version}] - {date}", 1)
    link = (
        f"{url}/compare/v{previous}...v{version}"
        if previous is not None
        else f"{url}/releases/tag/v{version}"
    )
    links = f"[Unreleased]: {url}/compare/v{version}...HEAD\n[{version}]: {link}"
    changelog, count = re.subn(r"^\[Unreleased\]: .*$", links, changelog, count=1, flags=re.M)
    if count == 0:
        changelog = changelog.rstrip("\n") + f"\n\n{links}\n"
    return changelog


def prepare(repo: Path, version: str | None, date: str, *, dry_run: bool = False) -> str:
    """Prepare the release; return a summary with the next steps."""
    releases = read_releases(repo)
    revision = read_revision(repo)
    changelog = (repo / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = unreleased_notes(changelog)
    if not re.search(r"^- ", notes, re.MULTILINE):
        raise ReleaseError("The [Unreleased] section of CHANGELOG.md is empty")
    datetime.date.fromisoformat(date)
    if releases:
        last = max(releases, key=lambda entry: parse_version(str(entry["version"])))
        previous: str | None = str(last["version"])
        changes = collect_changes(repo, last)
        if changes.commits == 0:
            raise ReleaseError(f"Nothing to release since v{previous}")
        proposed, reason = next_version(str(previous), changes)
        if changes.revision and "ENGINE_REVISION" not in notes:
            raise ReleaseError("ENGINE_REVISION changed: note it in the [Unreleased] section")
    else:
        previous = None
        proposed, reason = read_version(repo), "first release"
    version = version or proposed
    if previous is not None and parse_version(version) <= parse_version(previous):
        raise ReleaseError(f"Version {version} does not follow {previous}")
    parse_version(version)
    summary = [f"Release {version} ({reason}; proposed: {proposed}), dated {date}."]
    if not dry_run:
        url = repository_url(repo)
        (repo / "CHANGELOG.md").write_text(
            date_changelog(changelog, version, date, previous, url), encoding="utf-8"
        )
        init = repo / VERSION_FILE
        init.write_text(
            VERSION_PATTERN.sub(f'__version__ = "{version}"', init.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
        toml = repo / "releases.toml"
        entry = (
            f'[[releases]]\nversion = "{version}"\nengine_revision = {revision}\ndate = {date}\n'
        )
        current = toml.read_text(encoding="utf-8").rstrip("\n") if toml.is_file() else ""
        toml.write_text(f"{current}\n\n{entry}" if current else entry, encoding="utf-8")
        summary += [
            "Next steps:",
            f"  git switch -c chore/release-{version}",
            f'  git commit -s -am "chore(release): {version}"',
            "  open a pull request and merge it, then on the merge commit of main:",
            f'  git tag -a v{version} -m "Fakeverse {version}" && git push origin v{version}',
        ]
    return "\n".join(summary)


def check(repo: Path, tag: str) -> list[str]:
    """Problems that prevent publishing ``tag`` (empty when the release is consistent)."""
    try:
        version, revision = read_version(repo), read_revision(repo)
    except ReleaseError as error:
        return [str(error)]
    problems: list[str] = []
    if tag != f"v{version}":
        problems.append(f"Tag {tag} does not match the package version {version}")
    entry = next((e for e in read_releases(repo) if str(e.get("version")) == version), None)
    if entry is None:
        return [*problems, f"releases.toml has no entry for {version}"]
    if int(str(entry.get("engine_revision", -1))) != revision:
        problems.append(
            f"releases.toml lists {version} with engine revision {entry.get('engine_revision')}, "
            f"but ENGINE_REVISION is {revision}"
        )
    heading = f"## [{version}] - {entry.get('date')}"
    changelog_path = repo / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8") if changelog_path.is_file() else ""
    if heading not in changelog.splitlines():
        problems.append(f"CHANGELOG.md has no '{heading}' section")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", type=Path, default=Path("."), help="Repository root.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare", help="Prepare the next release.")
    prepare_parser.add_argument("--version", help="Version to release instead of the proposal.")
    prepare_parser.add_argument(
        "--date", default=datetime.date.today().isoformat(), help="Release date (YYYY-MM-DD)."
    )
    prepare_parser.add_argument("--dry-run", action="store_true", help="Only show the proposal.")
    check_parser = commands.add_parser("check", help="Check a release tag before publishing.")
    check_parser.add_argument("tag", help="Release tag, e.g. v0.1.0.")
    notes_parser = commands.add_parser("notes", help="Print the changelog of a version.")
    notes_parser.add_argument("version", help="Released version, e.g. 0.1.0.")
    args = parser.parse_args(argv)
    if args.command == "notes":
        changelog = (args.repo / "CHANGELOG.md").read_text(encoding="utf-8")
        try:
            print(section(changelog, f"## [{args.version}] - "))
        except ReleaseError as error:
            print(f"error: {error}")
            return 1
        return 0
    if args.command == "check":
        problems = check(args.repo, args.tag)
        for problem in problems:
            print(f"error: {problem}")
        if not problems:
            print(f"{args.tag}: OK")
        return 1 if problems else 0
    try:
        print(prepare(args.repo, args.version, args.date, dry_run=args.dry_run))
    except (ReleaseError, ValueError) as error:
        print(f"error: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
