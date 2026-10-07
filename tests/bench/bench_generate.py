"""Simple benchmark of the engine; not part of the test suite.

Target: p95 under 50 ms for 100 ``person`` on a modest CPU.

    uv run python tests/bench/bench_generate.py [UNIVERSES_DIR] [UNIVERSE]
"""

import statistics
import sys
import time
from pathlib import Path

from fakeverse import Fakeverse

ROUNDS = 200
TARGET_MS = 50.0


def main() -> int:
    root = Path(__file__).parents[2]
    directory = Path(sys.argv[1]) if len(sys.argv) > 1 else root / "tests/fixtures/universes"
    fakeverse = Fakeverse(directory)
    universe = sys.argv[2] if len(sys.argv) > 2 else fakeverse.universes()[0].id
    generator = fakeverse.universe(universe)
    durations = []
    for seed in range(ROUNDS):
        start = time.perf_counter()
        generator.generate("person", 100, seed)
        durations.append((time.perf_counter() - start) * 1000)
    p50 = statistics.median(durations)
    p95 = statistics.quantiles(durations, n=20)[-1]
    print(f"{universe}: 100 person, {ROUNDS} rounds: p50 {p50:.1f} ms, p95 {p95:.1f} ms")
    print("OK" if p95 < TARGET_MS else f"Above the {TARGET_MS:.0f} ms target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
