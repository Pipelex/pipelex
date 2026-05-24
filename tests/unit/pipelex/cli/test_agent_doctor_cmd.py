"""Unit tests for the agent CLI doctor command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_cli_factory import AGENT_CLI_STDERR_LOG_FIELDS
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport
from pipelex.system.console_target import ConsoleTarget


class TestAgentDoctorCmd:
    """Tests for agent_doctor_cmd JSON output."""

    @pytest.fixture(autouse=True)
    def _mock_doctor_bootstrap(self, mocker: MockerFixture) -> None:
        """Stub the runtime bootstrap so unit tests don't load real config or reconfigure logging.

        ``setup_doctor_runtime`` instantiates a PipelexHub, loads config from disk, and
        calls ``log.configure`` (once-per-process). ``apply_agent_cli_output_discipline``
        mutates global PrettyPrinter mode and the hub's console target. Both are out of
        scope for these tests — they cover the command's output shape, not the runtime
        bootstrap mechanics.
        """
        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.apply_agent_cli_output_discipline")

    def test_healthy_output_json(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Healthy checks should produce JSON with all_healthy=true and no recommended_actions."""
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            return_value=(True, 0, "All config files present"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(True, "Telemetry configured"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(True, {}, "All backends healthy"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_models",
            return_value=(True, "Models valid", {}),
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["success"] is True
        assert parsed["all_healthy"] is True
        assert "recommended_actions" not in parsed

    def test_unhealthy_includes_recommended_actions(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Unhealthy telemetry should produce recommended_actions in the JSON output."""
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            return_value=(True, 0, "All config files present"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(False, "Config format has changed - run 'pipelex init telemetry' to update"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(True, {}, "All backends healthy"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_models",
            return_value=(True, "Models valid", {}),
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["all_healthy"] is False
        assert parsed["checks"]["telemetry"]["healthy"] is False
        assert "recommended_actions" in parsed
        assert any("pipelex init telemetry" in action for action in parsed["recommended_actions"])
        # Rich markup should be stripped from the message
        assert "[cyan]" not in parsed["checks"]["telemetry"]["message"]

    def test_backend_details_in_output(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """Backend credential reports should appear as structured data in the JSON output."""
        credential_reports = {
            "anthropic": BackendCredentialsReport(
                backend_name="anthropic",
                required_vars=["ANTHROPIC_API_KEY"],
                missing_vars=["ANTHROPIC_API_KEY"],
                placeholder_vars=[],
                all_credentials_valid=False,
            ),
        }
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            return_value=(True, 0, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(True, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(False, credential_reports, "1 backend has issues"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_models",
            return_value=(True, "Models valid", {}),
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["all_healthy"] is False
        backends = parsed["checks"]["backend_credentials"]["backends"]
        assert len(backends) == 1
        assert backends[0]["backend_name"] == "anthropic"
        assert backends[0]["all_credentials_valid"] is False
        assert backends[0]["missing_vars"] == ["ANTHROPIC_API_KEY"]
        assert any("ANTHROPIC_API_KEY" in action for action in parsed["recommended_actions"])

    def test_unexpected_error_produces_json_error(self, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]) -> None:
        """If a health check raises an unexpected exception, agent_error JSON should be produced."""
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            side_effect=RuntimeError("unexpected kaboom"),
        )

        with pytest.raises(typer.Exit) as exc_info:
            agent_doctor_cmd(output_format=CliOutputFormat.JSON)
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert "unexpected kaboom" in parsed["message"]

    def test_bootstrap_pins_console_targets_to_stderr(self, mocker: MockerFixture) -> None:
        """Regression: agent_doctor_cmd must pass AGENT_CLI_STDERR_LOG_FIELDS to setup_doctor_runtime.

        The original bug: agent_doctor_cmd bypassed the agent CLI stdout-hardening that
        every other agent CLI command receives via make_pipelex_for_agent_cli. Doctor's
        check_models internally called log.configure with the user's raw log_config, so a
        user with console_log_target = "stdout" and a raised pipelex log level got log
        lines on stdout before the JSON envelope — breaking json.loads(stdout) for any
        downstream consumer.

        This test asserts that agent_doctor_cmd now folds the stderr overrides into the
        bootstrap call, so log/print targets are pinned before any check can fire.
        """
        # Re-mock setup_doctor_runtime so we can capture its call args
        # (the autouse fixture also mocks it, but we need the fresh handle here).
        mock_setup = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            return_value=(True, 0, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(True, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(True, {}, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_models",
            return_value=(True, "OK", {}),
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        mock_setup.assert_called_once_with(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS)
        # Pin the contract of the field dict itself: both Rich-managed channels must be stderr.
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"] is ConsoleTarget.STDERR
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_print_target"] is ConsoleTarget.STDERR
