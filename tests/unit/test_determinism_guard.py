"""Static guard for determinism in the generation path, complementing ruff's banned-api.

Ruff bans the ``random``, ``secrets``, ``uuid4`` and clock imports; this test catches what an
import rule cannot: random-like method calls, ``hash()`` and iteration over sets.
"""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[2] / "src" / "fakeverse"
RANDOM_METHODS = {"choice", "choices", "randint", "randrange", "shuffle", "sample", "random"}
SET_BUILDERS = {"set", "frozenset"}


def violations(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in RANDOM_METHODS:
                found.append(f"line {node.lineno}: call to .{func.attr}()")
            if isinstance(func, ast.Name) and func.id == "hash":
                found.append(f"line {node.lineno}: call to hash()")
        iterables: list[ast.expr] = []
        if isinstance(node, ast.For | ast.AsyncFor):
            iterables.append(node.iter)
        if isinstance(node, ast.comprehension):
            iterables.append(node.iter)
        for iterable in iterables:
            is_set = isinstance(iterable, ast.Set | ast.SetComp) or (
                isinstance(iterable, ast.Call)
                and isinstance(iterable.func, ast.Name)
                and iterable.func.id in SET_BUILDERS
            )
            if is_set:
                found.append(f"line {iterable.lineno}: iteration over a set")
    return found


SOURCES = sorted(path for path in SRC.rglob("*.py") if path.name != "rng.py")


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(SRC)))
def test_no_forbidden_construct(path: Path) -> None:
    assert violations(ast.parse(path.read_text(), str(path))) == []


@pytest.mark.parametrize(
    "source",
    [
        "rng.choice(items)",
        "random.shuffle(items)",
        "hash(value)",
        "for x in {1, 2}: pass",
        "[x for x in set(items)]",
        "{x for x in frozenset(items)}",
        "for x in {y for y in items}: pass",
    ],
)
def test_guard_detects(source: str) -> None:
    assert violations(ast.parse(source))
