"""Shared fixtures for agent CLI unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.tools.log.log_levels import LogLevel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


@pytest.fixture
def agent_ctx(mocker: MockerFixture) -> Any:
    """Create a mock typer.Context with log_level in obj, for direct command-function calls."""
    ctx = mocker.MagicMock()
    ctx.obj = {"log_level": LogLevel.WARNING}
    return ctx
