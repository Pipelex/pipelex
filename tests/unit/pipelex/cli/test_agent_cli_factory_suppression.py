"""Tests for verbose output suppression in the agent CLI factory."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode


class TestAgentCliFactorySuppression:
    """After successful init, the factory should silence pretty-print and Python logging."""

    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """Save and restore PrettyPrinter.mode and the process-global logging disable
        threshold around each test so the agent CLI cutoff does not leak into the rest
        of the suite.
        """
        original_mode = PrettyPrinter.mode
        original_disable = logging.root.manager.disable
        yield
        PrettyPrinter.mode = original_mode
        logging.disable(original_disable)

    def test_sets_silent_pretty_print_mode(self, mocker: MockerFixture) -> None:
        """PrettyPrinter.mode should be SILENT after make_pipelex_for_agent_cli succeeds."""
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)

        make_pipelex_for_agent_cli()

        assert PrettyPrinter.mode is PrettyPrintMode.SILENT

    def test_silences_every_logger_via_global_logging_disable(self, mocker: MockerFixture) -> None:
        """The factory must arm ``logging.disable`` so no record can be emitted by any
        logger — pipelex, anthropic, httpx, botocore, openai, or anything a transitive
        dependency creates. There is no log_level parameter; suppression is unconditional.

        Checks the observable behavior (``isEnabledFor`` short-circuits to False), not
        the per-logger level — because under ``logging.disable`` the per-logger level is
        irrelevant by design.
        """
        mock_pipelex = mocker.MagicMock()
        mocker.patch("pipelex.cli.agent_cli.commands.agent_cli_factory.Pipelex.make", return_value=mock_pipelex)
        # Arm a few loggers at INFO/WARNING as a downstream library might.
        for logger_name in ("pipelex", "anthropic", "httpx", "some.unknown.transitive.dep"):
            logging.getLogger(logger_name).setLevel(logging.DEBUG)

        make_pipelex_for_agent_cli()

        for logger_name in ("pipelex", "anthropic", "httpx", "some.unknown.transitive.dep"):
            assert not logging.getLogger(logger_name).isEnabledFor(logging.INFO), (
                f"logger '{logger_name}' must be silenced by the agent CLI global cutoff; "
                f"any record it emits leaks to stderr and corrupts the JSON error envelope."
            )
