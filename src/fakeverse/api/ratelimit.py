"""In-memory token bucket rate limiting, by client IP.

The state is local to the process: run the API as a single process (one Uvicorn worker).
"""

from __future__ import annotations

import ipaddress
import math
import time
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from fakeverse.api.settings import Network

MAX_TRACKED: Final[int] = 10_000

type Clock = Callable[[], float]


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of a request against the rate limit."""

    allowed: bool
    limit: int
    remaining: int
    reset: int
    """Seconds until the bucket is full again."""
    retry_after: int
    """Seconds until a request is allowed again (0 when allowed)."""

    def headers(self) -> dict[str, str]:
        headers = {
            "RateLimit-Limit": str(self.limit),
            "RateLimit-Remaining": str(self.remaining),
            "RateLimit-Reset": str(self.reset),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


@dataclass(slots=True)
class RateLimiter:
    """Token buckets of ``burst`` tokens, refilled at ``rate`` tokens per second.

    At most ``MAX_TRACKED`` buckets are kept; the least recently used one is evicted first.
    """

    rate: float
    burst: int
    clock: Clock = time.monotonic
    _buckets: OrderedDict[str, _Bucket] = field(default_factory=OrderedDict)

    def check(self, key: str) -> Decision:
        """Consume a token for ``key`` if one is available."""
        now = self.clock()
        bucket = self._buckets.get(key)
        if bucket is None:
            while len(self._buckets) >= MAX_TRACKED:
                self._buckets.popitem(last=False)
            bucket = self._buckets[key] = _Bucket(float(self.burst), now)
        else:
            self._buckets.move_to_end(key)
            bucket.tokens = min(self.burst, bucket.tokens + (now - bucket.updated) * self.rate)
            bucket.updated = now
        allowed = bucket.tokens >= 1
        if allowed:
            bucket.tokens -= 1
        retry_after = 0 if allowed else math.ceil((1 - bucket.tokens) / self.rate)
        return Decision(
            allowed=allowed,
            limit=self.burst,
            remaining=math.floor(bucket.tokens),
            reset=math.ceil((self.burst - bucket.tokens) / self.rate),
            retry_after=retry_after,
        )


def client_ip(peer: str | None, forwarded_for: str | None, trusted: Sequence[Network]) -> str:
    """Return the client IP.

    ``X-Forwarded-For`` is only used when the connection comes from a trusted proxy; the
    client is then the rightmost address that is not a trusted proxy.
    """
    if peer is None:
        return "unknown"
    if not forwarded_for or not _is_trusted(peer, trusted):
        return peer
    for candidate in reversed([part.strip() for part in forwarded_for.split(",")]):
        if candidate and not _is_trusted(candidate, trusted):
            return candidate
    return peer


def _is_trusted(address: str, trusted: Sequence[Network]) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in network for network in trusted)


def rate_key(address: str) -> str:
    """Rate limit key of a client: its IPv4 address, or its IPv6 /64 network.

    An IPv6 client usually controls a whole /64; keying by address would let it multiply its
    quota at will.
    """
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv4Address):
        return str(ip)
    if ip.ipv4_mapped is not None:  # ::ffff:a.b.c.d from dual-stack sockets
        return str(ip.ipv4_mapped)
    return str(ipaddress.ip_network(f"{ip}/64", strict=False))


def truncate_ip(address: str) -> str:
    """Mask the last IPv4 byte or the last IPv6 group, for logs."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    prefix = 24 if isinstance(ip, ipaddress.IPv4Address) else 112
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False).network_address)
