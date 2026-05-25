"""Unit tests for apply_agent_cli_output_discipline real side effects.

The discipline helper is the single source of truth for "agent CLI stdout stays clean."
The existing test_agent_doctor_cmd suite asserts the helper is called, but the autouse
fixture there stubs the helper out — so a typo regression inside the helper would ship
green. This module covers the real side effects (log redirect, PrettyPrinter mode flip,
hub print-target swap) by patching the dependencies the helper touches and asserting
the helper drives them correctly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import apply_agent_cli_output_discipline
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode


class TestApplyAgentCliOutputDiscipline:
    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """Restore PrettyPrinter.mode and the pipelex logger level after each test."""
        original_mode = PrettyPrinter.mode
        pipelex_logger = logging.getLogger("pipelex")
        original_level = pipelex_logger.level
        yield
        PrettyPrinter.mode = original_mode
        pipelex_logger.setLevel(original_level)

    def test_pins_console_print_target_to_stderr_when_hub_installed(self, mocker: MockerFixture) -> None:
        """When a hub is installed, the helper must pin its console_print_target to STDERR."""
        mock_redirect = mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.log.redirect_to_stderr")
        mock_hub = mocker.MagicMock()
        mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.PipelexHub.get_optional_instance",
            return_value=mock_hub,
        )

        apply_agent_cli_output_discipline()

        mock_redirect.assert_called_once()
        mock_hub.set_console_print_target.assert_called_once_with(target=ConsoleTarget.STDERR)
        assert PrettyPrinter.mode is PrettyPrintMode.SILENT
        assert logging.getLogger("pipelex").level == LogLevel.OFF.int_logging_level

    def test_no_hub_path_skips_hub_call_safely(self, mocker: MockerFixture) -> None:
        """When no hub is installed (broken-config doctor path), the helper must still pin
        log + PrettyPrinter without raising — the hub call is gated on get_optional_instance.
        """
        mock_redirect = mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.log.redirect_to_stderr")
        mocker.patch(
            "pipelex.cli.agent_cli.commands.agent_cli_factory.PipelexHub.get_optional_instance",
            return_value=None,
        )

        apply_agent_cli_output_discipline()

        mock_redirect.assert_called_once()
        assert PrettyPrinter.mode is PrettyPrintMode.SILENT
        assert logging.getLogger("pipelex").level == LogLevel.OFF.int_logging_level
