"""HTTP caching of generations.

A request with an explicit seed is deterministic, hence cacheable.
"""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import blake2b

from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.rng import canonical_json

IMMUTABLE = "public, max-age=31536000, immutable"
ONE_HOUR = "public, max-age=3600"
NO_STORE = "no-store"


def cache_control(*, seed_given: bool, data_version_given: bool) -> str:
    """``Cache-Control`` of a generation."""
    if not seed_given:
        return NO_STORE
    return IMMUTABLE if data_version_given else ONE_HOUR


def etag(path: str, data_version: str, params: Mapping[str, object]) -> str:
    """Strong ETag: hash of the canonical request, with the resolved data version and the
    engine revision."""
    canonical = canonical_json([ENGINE_REVISION, data_version, path, dict(params)])
    return '"' + blake2b(canonical, digest_size=16).hexdigest() + '"'


def matches(if_none_match: str | None, tag: str) -> bool:
    """Whether an ``If-None-Match`` header matches ``tag`` (weak comparison)."""
    if not if_none_match:
        return False
    candidates = [part.strip() for part in if_none_match.split(",")]
    return "*" in candidates or tag in [c.removeprefix("W/") for c in candidates]
