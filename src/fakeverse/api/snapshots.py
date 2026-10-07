"""Data snapshots served by the API.

Each snapshot is the data of one ``data_version``. With ``FAKEVERSE_DATA_DIR``, snapshots are
the subdirectories ``<version>/`` of that directory (``releases.toml`` may sit next to them);
otherwise there is a single snapshot: the package data, at the package version. Snapshots of a
release made with an older engine revision are retired.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fakeverse import __version__
from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.errors import DataVersionNotFound, DataVersionRetired, UniverseNotFound
from fakeverse.fakeverse import Fakeverse, UniverseGenerator
from fakeverse.releases import (
    is_semver,
    packaged_releases_file,
    read_releases,
    semver_key,
)


@dataclass(slots=True)
class SnapshotStore:
    """The data versions available to the API."""

    snapshots: dict[str, Fakeverse]
    """Snapshots by data version, newest first."""
    retired: dict[str, int]
    """Known releases of older engine revisions, with their revision."""
    disabled: tuple[str, ...] = ()

    @classmethod
    def load(cls, data_dir: Path | None, disabled: list[str]) -> SnapshotStore:
        releases_file = (
            data_dir / "releases.toml"
            if data_dir is not None and (data_dir / "releases.toml").is_file()
            else packaged_releases_file()
        )
        releases = read_releases(releases_file)
        retired = {
            r.version: r.engine_revision for r in releases if r.engine_revision != ENGINE_REVISION
        }
        snapshots: dict[str, Fakeverse] = {}
        if data_dir is None:
            snapshots[__version__] = Fakeverse()
        else:
            for directory in sorted(data_dir.iterdir()):
                if (
                    directory.is_dir()
                    and is_semver(directory.name)
                    and directory.name not in retired
                ):
                    snapshots[directory.name] = Fakeverse(directory, directory.name)
        ordered = dict(
            sorted(snapshots.items(), key=lambda item: semver_key(item[0]), reverse=True)
        )
        return cls(ordered, retired, tuple(disabled))

    @property
    def versions(self) -> list[str]:
        """Served data versions, oldest first."""
        return list(reversed(self.snapshots))

    @property
    def default_version(self) -> str:
        return next(iter(self.snapshots))

    def resolve_version(self, data_version: str | None) -> str:
        """Return the data version to use.

        Raises:
            DataVersionNotFound, DataVersionRetired.
        """
        if data_version is None:
            return self.default_version
        if data_version in self.snapshots:
            return data_version
        if data_version in self.retired:
            raise DataVersionRetired(
                f"Data version {data_version} was produced by engine revision "
                f"{self.retired[data_version]} and is no longer served (current revision: "
                f"{ENGINE_REVISION}). Use the package pinned to this version: "
                f"pip install fakeverse=={data_version}."
            )
        raise DataVersionNotFound(
            f"Unknown data version '{data_version}'. Available: {', '.join(self.versions)}."
        )

    def fakeverse(self, data_version: str) -> Fakeverse:
        return self.snapshots[data_version]

    def universe_ids(self, data_version: str) -> list[str]:
        """Enabled universes of a snapshot."""
        return [
            info.id
            for info in self.fakeverse(data_version).universes()
            if info.id not in self.disabled
        ]

    def generator(self, data_version: str, universe: str, locale: str | None) -> UniverseGenerator:
        """Return a generator; a disabled universe does not exist.

        Raises:
            UniverseNotFound, LocaleNotSupported, InvalidOption.
        """
        enabled = self.universe_ids(data_version)
        if universe not in enabled:
            available = ", ".join(enabled) or "none"
            raise UniverseNotFound(f"Unknown universe '{universe}'. Available: {available}.")
        return self.fakeverse(data_version).universe(universe, locale)
