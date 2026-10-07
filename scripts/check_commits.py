"""Check commit messages: Conventional Commits and Developer Certificate of Origin sign-off.

    python scripts/check_commits.py --message-file .git/COMMIT_EDITMSG   # commit-msg hook
    python scripts/check_commits.py --range BASE..HEAD                     # commits of a PR
    python scripts/check_commits.py --title "feat: add a universe"        # title of a PR

A header reads ``type(scope)!: description``, at most 100 characters, without a final period.
Commits also need a ``Signed-off-by`` trailer (``git commit -s``). The title of a pull request
becomes the header of the squashed commit, so it follows the same format.

Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Final

TYPES: Final = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)
HEADER: Final = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9][a-z0-9-]*\))?!?: \S(?:.*\S)?$")
MAX_HEADER: Final = 100
SIGN_OFF: Final = re.compile(r"^Signed-off-by: .+ <.+>$", re.MULTILINE)
AUTOSQUASH: Final = ("fixup! ", "squash! ", "amend! ")


def header_problems(header: str) -> list[str]:
    """Problems of a commit header or pull request title."""
    if not HEADER.match(header):
        return [
            f"'{header}' does not follow Conventional Commits: 'type(scope): description' "
            f"with a type among {', '.join(TYPES)}"
        ]
    if len(header) > MAX_HEADER:
        return [f"'{header}' is longer than {MAX_HEADER} characters"]
    if header.endswith("."):
        return [f"'{header}' ends with a period"]
    return []


def message_problems(message: str, *, local: bool = False) -> list[str]:
    """Problems of a whole commit message. ``local`` tolerates merges and autosquash commits."""
    lines = [line for line in message.splitlines() if not line.startswith("#")]
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return ["The commit message is empty"]
    header = lines[0]
    if local and (header.startswith("Merge ") or header.startswith(AUTOSQUASH)):
        return []
    problems = header_problems(header)
    if len(lines) > 1 and lines[1].strip():
        problems.append(f"'{header}' must be followed by a blank line")
    if not SIGN_OFF.search("\n".join(lines)):
        problems.append(f"'{header}' is not signed off: commit with 'git commit -s'")
    return problems


def range_problems(revisions: str, repo: Path = Path(".")) -> list[str]:
    """Problems of every non-merge commit of a revision range."""
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--no-merges", "--format=%B%x1e", revisions],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [
        problem
        for message in log.split("\x1e")
        if message.strip()
        for problem in message_problems(message)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message-file", type=Path, help="Commit message file (commit-msg hook).")
    group.add_argument("--range", dest="revisions", help="Revision range, e.g. BASE..HEAD.")
    group.add_argument("--title", help="Title of a pull request.")
    args = parser.parse_args(argv)
    if args.message_file is not None:
        problems = message_problems(args.message_file.read_text(encoding="utf-8"), local=True)
    elif args.revisions is not None:
        problems = range_problems(args.revisions)
    else:
        problems = header_problems(args.title)
    for problem in problems:
        print(f"error: {problem}")
    if problems:
        print("See CONTRIBUTING.md, section 'Commits'.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
