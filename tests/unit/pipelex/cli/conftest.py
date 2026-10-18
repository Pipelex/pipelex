"""Shared fixtures for agent CLI unit tests."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.agent_cli.commands.agent_output import start_agent_cli_error_format
from pipelex.cli.error_handlers import set_traceback_requested

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def reset_traceback_requested() -> Iterator[None]:
    """Keep the --traceback ContextVar from leaking between cli/ tests.

    ``PipelexCLI.make_context`` (and tests that call ``set_traceback_requested``) set
    this flag; without a reset a leaked ``True`` would make a sibling test's "no flag"
    assertion order-dependent.
    """
    set_traceback_requested(value=False)
    yield
    set_traceback_requested(value=False)


@pytest.fixture(autouse=True)
def reset_agent_cli_error_format() -> Iterator[None]:
    """Keep the error-format ContextVars, the program's and the active one, from leaking between cli/ tests.

    The deeper ``agent_cli/`` conftest has the same fixture, but tests directly under
    ``cli/`` (e.g. ``test_agent_output.py``, which sets the ContextVar to MARKDOWN)
    are not covered by it — without this, a leaked MARKDOWN format would make a
    sibling test's JSON-format assertion order-dependent.
    """
    start_agent_cli_error_format()
    yield
    start_agent_cli_error_format()


@pytest.fixture(autouse=True)
def restore_logging_cutoff() -> Iterator[None]:
    """Keep the agent CLI's process-global ``logging.disable`` cutoff from leaking out of cli/ tests.

    A test that runs ``pipelex-agent`` in-process, through its app callback, ``make_pipelex_for_agent_cli`` or the
    doctor, arms ``silence_logging_for_agent_cli``, which raises ``logging.root.manager.disable`` to ``sys.maxsize``
    for the whole process. A real agent CLI process exits right after, but a test session goes on, so without this
    restore every log-capture test that runs later, in any directory, would see no record at all.
    """
    original_disable = logging.root.manager.disable
    yield
    logging.disable(original_disable)
