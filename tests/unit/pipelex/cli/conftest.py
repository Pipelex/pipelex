"""Shared fixtures for agent CLI unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, set_agent_cli_error_format

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def reset_agent_cli_error_format() -> Iterator[None]:
    """Keep the module-level error-format ContextVar from leaking between cli/ tests.

    The deeper ``agent_cli/`` conftest has the same fixture, but tests directly under
    ``cli/`` (e.g. ``test_agent_output.py``, which sets the ContextVar to MARKDOWN)
    are not covered by it — without this, a leaked MARKDOWN format would make a
    sibling test's JSON-format assertion order-dependent.
    """
    set_agent_cli_error_format(CliOutputFormat.JSON)
    yield
    set_agent_cli_error_format(CliOutputFormat.JSON)
