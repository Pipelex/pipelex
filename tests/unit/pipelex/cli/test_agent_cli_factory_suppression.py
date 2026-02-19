"""Tests for verbose output suppression in the agent CLI factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.tools.log.log_levels import LogLevel
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode


class TestAgentCliFactorySuppression:
    """After successful init, the factory should silence pretty-print and lower log verbosity."""

    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """Save and restore PrettyPrinter.mode and pipelex log level around each test."""
        original_mode = PrettyPrinter.mode
        pipelex_logger = logging.getLogger("pipelex")
        original_level: int = pipelex_logger.level
        yield
        PrettyPrinter.mode = original_mode
        pipelex_logger.setLevel(original_level)

    def test_sets_silent_pretty_print_mode(self, mocker: MockerFixture) -> None:
        """PrettyPrinter.mode should be SILENT after make_pipelex_for_agent_cli succeeds."""
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)

        make_pipelex_for_agent_cli()

        assert PrettyPrinter.mode is PrettyPrintMode.SILENT

    def test_sets_warning_log_level(self, mocker: MockerFixture) -> None:
        """Log level should be WARNING by default after make_pipelex_for_agent_cli succeeds."""
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)

        make_pipelex_for_agent_cli()

        pipelex_logger = logging.getLogger("pipelex")
        assert pipelex_logger.level == logging.WARNING
        assert pipelex_logger.level == LogLevel.WARNING.int_logging_level

    def test_sets_custom_log_level(self, mocker: MockerFixture) -> None:
        """Log level should match the provided log_level parameter."""
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)

        make_pipelex_for_agent_cli(log_level=LogLevel.DEBUG)

        pipelex_logger = logging.getLogger("pipelex")
        assert pipelex_logger.level == logging.DEBUG
        assert pipelex_logger.level == LogLevel.DEBUG.int_logging_level
