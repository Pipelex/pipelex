import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
    from importlib.resources.abc import Traversable
    from typing import Self
else:
    from importlib.abc import Traversable  # type: ignore[attr-defined]

    from backports.strenum import StrEnum  # type: ignore[import-not-found, no-redef]
    from typing_extensions import Self  # type: ignore[assignment]

__all__ = ["Self", "StrEnum", "Traversable"]
