try:
    from typing import Self  # Python 3.11+
except ImportError:  # Python 3.10
    from typing_extensions import Self  # type: ignore[assignment]

try:
    from enum import StrEnum  # Python 3.11+
except ImportError:  # Python 3.10
    from backports.strenum import StrEnum  # type: ignore[assignment, import-not-found, no-redef]

__all__ = ["Self", "StrEnum"]
