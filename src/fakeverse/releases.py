"""Release history (``releases.toml``) and SemVer helpers."""

from __future__ import annotations

import datetime
import re
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def is_semver(version: str) -> bool:
    """Whether ``version`` is a SemVer 2.0.0 version."""
    return _SEMVER.match(version) is not None


type SemverKey = tuple[int, int, int, int, tuple[tuple[int, int | str], ...]]


def semver_key(version: str) -> SemverKey:
    """Sort key following SemVer 2.0.0 precedence.

    A pre-release sorts before its release; pre-release identifiers compare numerically when
    they are numbers, lexically otherwise, numbers first (``rc.2`` < ``rc.10``).

    Raises:
        ValueError: if ``version`` is not SemVer.
    """
    match = _SEMVER.match(version)
    if match is None:
        raise ValueError(f"Not a SemVer version: {version!r}")
    major, minor, patch, pre = match.groups()
    identifiers: tuple[tuple[int, int | str], ...] = tuple(
        (0, int(part)) if part.isdigit() else (1, part) for part in (pre or "").split(".") if pre
    )
    return int(major), int(minor), int(patch), 0 if pre else 1, identifiers


@dataclass(frozen=True, slots=True)
class Release:
    """A published release."""

    version: str
    engine_revision: int
    date: datetime.date


def read_releases(path: Path) -> list[Release]:
    """Read a ``releases.toml`` file; a missing file means no release."""
    if not path.is_file():
        return []
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    releases = []
    for entry in document.get("releases", []):
        version = str(entry["version"])
        if not is_semver(version):
            raise ValueError(f"releases.toml: invalid version {version!r}")
        releases.append(Release(version, int(entry["engine_revision"]), _as_date(entry["date"])))
    return releases


def _as_date(value: object) -> datetime.date:
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value))


def packaged_releases_file() -> Path:
    """Return ``releases.toml`` as shipped in the wheel, or from the source checkout."""
    packaged = files("fakeverse").joinpath("_releases.toml")
    if isinstance(packaged, Path) and packaged.is_file():
        return packaged
    return Path(__file__).resolve().parents[2] / "releases.toml"
