"""Model combination type for test fixtures."""

from __future__ import annotations

from typing import NamedTuple


class ModelCombo(NamedTuple):
    """A model/backend combination for parametrized tests."""

    handle: str
    backend: str
