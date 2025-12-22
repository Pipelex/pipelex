try:
    from typing import Self  # Python 3.11+
except ImportError:  # Python 3.10
    from typing_extensions import Self  # type: ignore[assignment]

try:
    from enum import StrEnum  # Python 3.11+
except ImportError:  # Python 3.10
    from backports.strenum import StrEnum  # type: ignore[assignment, import-not-found, no-redef]

try:
    from importlib.resources.abc import Traversable  # Python 3.11+
except ModuleNotFoundError:  # Python 3.10
    from importlib.abc import Traversable  # type: ignore[assignment, no-redef]

__all__ = ["Self", "StrEnum", "Traversable"]
