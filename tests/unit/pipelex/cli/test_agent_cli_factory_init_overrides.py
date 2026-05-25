"""Tests for init-time log suppression via config_overrides in the agent CLI factory.

Regression guard: a user TOML with ``[pipelex.log_config.package_log_levels] pipelex =
"DEBUG"`` used to leak setup-time logs (e.g. ``telemetry_factory.py``'s
``log.debug("Telemetry is disabled...")``, ``validation_error_categorizer.py``'s
``log.warning``) onto stderr — corrupting the JSON error envelope that downstream agent
consumers parse. The fix pins ``package_log_levels.pipelex = OFF`` via
``config_overrides`` so suppression takes effect from the very first ``log.configure``
call inside ``Pipelex.make``, not post-init via ``apply_agent_cli_output_discipline``.

The agent CLI has NO ``--log-level`` flag. Suppression is unconditional by design — the
CLI is machine-consumed and stderr is reserved for the structured error envelope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import (
    AGENT_CLI_STDERR_LOG_FIELDS,
    make_pipelex_for_agent_cli,
)
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_levels import LogLevel


class TestAgentCliFactoryInitOverrides:
    """Pins the contract that init-time logs are suppressed via config_overrides."""

    def test_static_leaf_pins_off_for_pipelex_package(self) -> None:
        """The doctor path and the full-init path BOTH use ``AGENT_CLI_STDERR_LOG_FIELDS``,
        so the leaf itself must silence pipelex logs at OFF.
        """
        assert AGENT_CLI_STDERR_LOG_FIELDS["default_log_level"] == LogLevel.OFF
        assert AGENT_CLI_STDERR_LOG_FIELDS["package_log_levels"]["pipelex"] == LogLevel.OFF
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"] is ConsoleTarget.STDERR
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_print_target"] is ConsoleTarget.STDERR

    def test_make_injects_off_overrides_into_pipelex_make(self, mocker: MockerFixture) -> None:
        """``Pipelex.make`` must receive a ``config_overrides`` carrying the OFF pins so
        suppression takes effect at ``log.configure`` time — before any setup-time
        ``log.*`` call can fire on stderr.
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
