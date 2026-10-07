"""Engine revision.

``ENGINE_REVISION`` identifies the behavior of the generation algorithm. It must be
incremented, and the change noted in CHANGELOG.md, whenever a code change alters the output
for identical inputs and data. The golden tests detect such changes.
"""

from typing import Final

ENGINE_REVISION: Final[int] = 1
