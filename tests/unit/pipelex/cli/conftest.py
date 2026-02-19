"""Shared fixtures for agent CLI unit tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pipelex.tools.log.log_levels import LogLevel


@pytest.fixture
def agent_ctx() -> Any:
    """Create a mock typer.Context with log_level in obj, for direct command-function calls."""
    ctx = MagicMock()
    ctx.obj = {"log_level": LogLevel.WARNING}
    return ctx
