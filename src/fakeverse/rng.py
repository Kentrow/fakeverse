"""The only source of randomness of Fakeverse.

:class:`Rng` wraps :class:`random.Random` and only calls ``getrandbits``, whose output is
stable across Python versions; every other primitive is implemented on top of it. Item seeds
are derived with BLAKE2b from a canonical JSON encoding of the generation inputs.
"""

from __future__ import annotations

import json
import random
import secrets
import string
from bisect import bisect_right
from collections.abc import Sequence
from hashlib import blake2b
from typing import Final

MAX_SEED: Final[int] = 2**63 - 1
"""Seeds are integers from 0 to 2^63 - 1."""

_LETTERS: Final[str] = string.ascii_uppercase


class Rng:
    """A deterministic random number generator seeded with an integer."""

    __slots__ = ("_random",)

    def __init__(self, seed: int) -> None:
        self._random = random.Random(seed)

    def below(self, n: int) -> int:
        """Return a uniform integer in ``[0, n)``, by rejection sampling.

        ``below(1)`` returns 0 without consuming randomness.
        """
        if n < 1:
            raise ValueError("n must be positive")
        bits = (n - 1).bit_length()
        if bits == 0:
            return 0
        while True:
            value = self._random.getrandbits(bits)
            if value < n:
                return value

    def int_between(self, low: int, high: int) -> int:
        """Return a uniform integer in ``[low, high]``."""
        if low > high:
            raise ValueError("low must not exceed high")
        return low + self.below(high - low + 1)

    def weighted_index(self, cumulative_weights: Sequence[int]) -> int:
        """Return an index drawn with the given cumulative weights."""
        return bisect_right(cumulative_weights, self.below(cumulative_weights[-1]))

    def digits(self, n: int) -> str:
        """Return ``n`` random digits."""
        return "".join(str(self.below(10)) for _ in range(n))

    def letters(self, n: int) -> str:
        """Return ``n`` random uppercase letters A-Z."""
        return "".join(_LETTERS[self.below(26)] for _ in range(n))


def canonical_json(value: object) -> bytes:
    """Encode ``value`` as canonical JSON: sorted keys, compact separators, UTF-8."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def derive_seed(*components: object) -> int:
    """Derive a 128-bit seed from JSON-serializable components."""
    digest = blake2b(canonical_json(list(components)), digest_size=16).digest()
    return int.from_bytes(digest, "big")


def random_seed() -> int:
    """Draw a fresh seed for a request without one. The only use of ``secrets``."""
    return secrets.randbits(63)
