#!/usr/bin/env bash
# Build the wheel and check it in an isolated environment, outside the source tree:
# embedded universes, CLI entry point and Faker provider.
# Usage: scripts/check_wheel.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
dist="$(mktemp -d)"
work="$(mktemp -d)"
trap 'rm -rf "$dist" "$work"' EXIT

uv build --wheel --out-dir "$dist" "$root" > /dev/null
wheel="$(ls "$dist"/fakeverse-*.whl)"
cd "$work"

run() { uv run --isolated --no-project --with "$wheel[faker]" "$@"; }

run fakeverse info
run fakeverse validate --strict
run fakeverse generate lotr person --seed 1 --locale fr > /dev/null
run python - <<'PY'
from faker import Faker

import fakeverse
from fakeverse import Fakeverse
from fakeverse.faker import FakeverseProvider
from fakeverse.loader import embedded_universes_dir

assert "site-packages" in str(embedded_universes_dir()), embedded_universes_dir()
assert [u.id for u in Fakeverse().universes()] == ["lotr", "starwars"]
fake = Faker("fr_FR")
fake.add_provider(FakeverseProvider)
assert fake.fakeverse("lotr").person()["people"]
print(f"fakeverse {fakeverse.__version__}: wheel OK")
PY
