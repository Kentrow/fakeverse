"""Fakeverse: coherent fake data generator themed by fictional universes."""

__version__ = "0.1.0"

from fakeverse.engine.revision import ENGINE_REVISION
from fakeverse.fakeverse import (
    Fakeverse,
    GenerationMeta,
    GenerationResult,
    UniverseGenerator,
    UniverseInfo,
)

__all__ = [
    "ENGINE_REVISION",
    "Fakeverse",
    "GenerationMeta",
    "GenerationResult",
    "UniverseGenerator",
    "UniverseInfo",
    "__version__",
]
