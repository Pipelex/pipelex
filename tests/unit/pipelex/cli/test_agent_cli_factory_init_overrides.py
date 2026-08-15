"""Tests for init-time log suppression via config_overrides in the agent CLI factory.

Regression guard: a user TOML with ``[runtime.log.package_log_levels] pipelex =
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
from pipelex.tools.misc.pretty import PrettyPrinter


class TestAgentCliFactoryInitOverrides:
    """Pins the contract that init-time logs are suppressed via global cutoff + overrides."""

    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """``make_pipelex_for_agent_cli`` mutates two pieces of process-global state:
        ``logging.disable`` (via ``silence_logging_for_agent_cli``) and
        ``PrettyPrinter.mode`` (set to ``SILENT`` by ``apply_agent_cli_output_discipline``
        at the end of the factory). Snapshot both and restore them after each test so
        the agent CLI's discipline does not leak into other test classes in the same
        xdist worker — under pytest-xdist the failure mode is downstream
        ``pretty_print``-based tests (e.g. ``test_json_content_rendering``) producing
        empty output and asserting ``'x' in ''``.
        """
        original_disable = logging.root.manager.disable
        original_pretty_mode = PrettyPrinter.mode
        yield
        logging.disable(original_disable)
        PrettyPrinter.mode = original_pretty_mode

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
        log_config_overrides = config_overrides["runtime"]["log"]
        assert log_config_overrides["default_log_level"] is LogLevel.OFF
        assert log_config_overrides["package_log_levels"]["pipelex"] is LogLevel.OFF
        assert log_config_overrides["console_log_target"] is ConsoleTarget.STDERR
        assert log_config_overrides["console_print_target"] is ConsoleTarget.STDERR

        assert logging.root.manager.disable == sys.maxsize, (
            "make_pipelex_for_agent_cli must call silence_logging_for_agent_cli (which arms "
            "logging.disable at sys.maxsize) BEFORE Pipelex.make — otherwise any "
            "third-party logger configured at INFO/WARNING leaks records during init."
        )
