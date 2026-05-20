"""Shared fixtures for agent CLI format tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def reset_agent_cli_error_format() -> Iterator[None]:
    """Keep the module-level error-format ContextVar from leaking between tests."""
    set_agent_cli_error_format(CliOutputFormat.JSON)
    yield
    set_agent_cli_error_format(CliOutputFormat.JSON)
