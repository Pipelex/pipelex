"""Tests for init-time log suppression via config_overrides in the agent CLI factory.

Regression guard: a user TOML with ``[pipelex.log_config.package_log_levels] pipelex =
"DEBUG"`` used to leak setup-time logs (e.g. ``telemetry_factory.py``'s
``log.debug("Telemetry is disabled...")``, ``validation_error_categorizer.py``'s
``log.warning``) onto stderr — corrupting the JSON error envelope that downstream agent
consumers parse. The bulletproof cutoff is ``silence_logging_for_agent_cli`` which is
called at the very start of every agent CLI entry point and uses
``logging.disable(sys.maxsize)`` — a process-global threshold that blocks any record
for any logger at any level (including custom levels above CRITICAL), regardless of
which package emits or what level it's configured at. The ``config_overrides`` carry
defense-in-depth pins on top.

The agent CLI has NO ``--log-level`` flag. Suppression is unconditional by design — the
CLI is machine-consumed and stderr is reserved for the structured error envelope.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import (
    AGENT_CLI_STDERR_LOG_FIELDS,
    make_pipelex_for_agent_cli,
)
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_levels import LogLevel


class TestAgentCliFactoryInitOverrides:
    """Pins the contract that init-time logs are suppressed via global cutoff + overrides."""

    @pytest.fixture(autouse=True)
    def _restore_global_logging_disable(self):
        """``make_pipelex_for_agent_cli`` mutates process-global state via
        ``logging.disable``. Snapshot the manager's disable level and restore it after
        each test so the agent CLI cutoff does not leak into other tests in the suite.
        """
        original_disable = logging.root.manager.disable
        yield
        logging.disable(original_disable)

    def test_static_leaf_pins_off_for_pipelex_package(self) -> None:
        """The doctor path and the full-init path BOTH use ``AGENT_CLI_STDERR_LOG_FIELDS``,
        so the leaf itself must silence pipelex logs at OFF as defense-in-depth on top of
        the global ``logging.disable`` cutoff.
        """
        assert AGENT_CLI_STDERR_LOG_FIELDS["default_log_level"] == LogLevel.OFF
        assert AGENT_CLI_STDERR_LOG_FIELDS["package_log_levels"]["pipelex"] == LogLevel.OFF
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"] is ConsoleTarget.STDERR
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_print_target"] is ConsoleTarget.STDERR

    def test_make_injects_overrides_and_arms_global_logging_cutoff(self, mocker: MockerFixture) -> None:
        """Two contracts in one call:

        1. ``Pipelex.make`` must receive a ``config_overrides`` carrying the OFF pins +
           stderr targets so the Rich channels are correctly aimed before any banner /
           table / pretty-print fires.
        2. ``silence_logging_for_agent_cli`` (called before ``Pipelex.make`` so the
           cutoff is active during init) must have armed ``logging.disable`` at
           ``sys.maxsize`` — the bulletproof handler-side cutoff that blocks every
           record for every logger at every level (including custom levels above
           CRITICAL), including third-party libraries we don't enumerate.
        """
        mock_pipelex = mocker.MagicMock()
        mock_make = mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make",
            return_value=mock_pipelex,
        )

        make_pipelex_for_agent_cli()

        config_overrides = mock_make.call_args.kwargs["config_overrides"]
        log_config_overrides = config_overrides["pipelex"]["log_config"]
        assert log_config_overrides["default_log_level"] is LogLevel.OFF
        assert log_config_overrides["package_log_levels"]["pipelex"] is LogLevel.OFF
        assert log_config_overrides["console_log_target"] is ConsoleTarget.STDERR
        assert log_config_overrides["console_print_target"] is ConsoleTarget.STDERR

        assert logging.root.manager.disable == sys.maxsize, (
            "make_pipelex_for_agent_cli must call silence_logging_for_agent_cli (which arms "
            "logging.disable at sys.maxsize) BEFORE Pipelex.make — otherwise any "
            "third-party logger configured at INFO/WARNING leaks records during init."
        )
