"""Unit tests for the agent CLI doctor command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
import typer

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cogt.model_backends.backend_library import BackendCredentialsReport


class TestAgentDoctorCmd:
    """Tests for agent_doctor_cmd JSON output."""

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
            agent_doctor_cmd()
        assert exc_info.value.exit_code == 1

        parsed = json.loads(capsys.readouterr().err)
        assert parsed["error"] is True
        assert "unexpected kaboom" in parsed["message"]
