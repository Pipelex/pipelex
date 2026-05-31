"""Unit tests for the agent CLI output discipline functions.

Covers two helpers:

  - ``silence_logging_for_agent_cli`` — process-global ``logging.disable`` cutoff that
    blocks any record for any logger, regardless of package or level. This is the
    bulletproof defense against third-party logger leaks (anthropic, httpx, botocore,
    openai, asyncio, ...) that we can't (and shouldn't try to) enumerate by name.
  - ``apply_agent_cli_output_discipline`` — pins the Rich/Pretty channels that are
    INDEPENDENT of Python's logging system (Rich Console for tables/banners,
    PrettyPrinter for pretty_print, hub-level console target).

The existing test_agent_doctor_cmd suite asserts these helpers are called, but the
autouse fixture there stubs them out — so a typo regression inside the helper itself
would ship green. This module covers the real side effects.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import (
    apply_agent_cli_output_discipline,
    silence_logging_for_agent_cli,
)
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.misc.pretty import PrettyPrinter, PrettyPrintMode

# Loggers armed by the test below at non-OFF levels. Their ``.level`` attribute is
# snapshot in the autouse fixture and restored after each test so the per-logger state
# does not leak into the rest of the suite (other tests may rely on the default NOTSET).
_ARMED_LOGGER_NAMES: tuple[str, ...] = (
    "anthropic",
    "httpx",
    "some.transitive.dep.we.never.heard.of",
)


class TestAgentCliOutputDiscipline:
    @pytest.fixture(autouse=True)
    def _restore_globals(self):
        """Restore PrettyPrinter.mode, the process-global ``logging.disable`` threshold,
        AND the per-logger ``.level`` for every logger this test class arms — otherwise
        the levels set on shared module-level loggers (``anthropic``, ``httpx``, ...) leak
        into other tests that assume default NOTSET.
        """
        original_mode = PrettyPrinter.mode
        original_disable = logging.root.manager.disable
        original_levels = {name: logging.getLogger(name).level for name in _ARMED_LOGGER_NAMES}
        yield
        PrettyPrinter.mode = original_mode
        logging.disable(original_disable)
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)

    def test_silence_logging_disables_every_third_party_logger_regardless_of_configured_level(self) -> None:
        """Regression: ``silence_logging_for_agent_cli`` must call ``logging.disable`` at
        ``sys.maxsize`` so that every logger — pipelex, anthropic, httpx, botocore,
        openai, anything a transitive dep ever creates — has ``isEnabledFor`` short-circuit
        to False before its own level check fires, at every level (including custom levels
        above CRITICAL). This is the only defense that scales without an enumeration of
        package names.
        """
        # Arm a couple of loggers at INFO/WARNING as if a downstream library had configured
        # them. The global disable must override their own level checks.
        anthropic_logger = logging.getLogger("anthropic")
        anthropic_logger.setLevel(logging.INFO)
        httpx_logger = logging.getLogger("httpx")
        httpx_logger.setLevel(logging.WARNING)
        # A name we never enumerate, to prove the defense is not list-based.
        random_logger = logging.getLogger("some.transitive.dep.we.never.heard.of")
        random_logger.setLevel(logging.DEBUG)

        silence_logging_for_agent_cli()

        assert logging.root.manager.disable == sys.maxsize
        assert not anthropic_logger.isEnabledFor(logging.INFO)
        assert not anthropic_logger.isEnabledFor(logging.CRITICAL)
        assert not httpx_logger.isEnabledFor(logging.WARNING)
        assert not random_logger.isEnabledFor(logging.DEBUG)
        assert not random_logger.isEnabledFor(logging.CRITICAL)

    def test_apply_discipline_pins_console_print_target_to_stderr_when_hub_installed(self, mocker: MockerFixture) -> None:
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

    def test_apply_discipline_no_hub_path_skips_hub_call_safely(self, mocker: MockerFixture) -> None:
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
