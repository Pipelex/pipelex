"""Shared fixtures for agent CLI integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.agent_output import start_agent_cli_error_format

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def reset_agent_cli_error_format() -> Iterator[None]:
    """Keep the error-format ContextVars, the program's and the active one, from leaking between tests."""
    start_agent_cli_error_format()
    yield
    start_agent_cli_error_format()
