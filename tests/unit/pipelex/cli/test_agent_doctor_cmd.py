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
        """Stub the runtime bootstrap so unit tests don't load real config or mutate
        global logging / PrettyPrinter state.

        ``setup_doctor_runtime`` instantiates a RuntimeHub, loads config from disk, and
        calls ``log.configure`` (once-per-process). ``apply_agent_cli_output_discipline``
        mutates global PrettyPrinter mode and the hub's console target.
        ``silence_logging_for_agent_cli`` arms ``logging.disable`` at ``sys.maxsize``
        — process-global and would leak into other tests in the suite. All three are
        out of scope for these tests — they cover the command's output shape, not the
        runtime bootstrap mechanics.
        """
        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.apply_agent_cli_output_discipline")
        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.silence_logging_for_agent_cli")

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

    def test_broken_config_skips_bootstrap_and_preserves_partial_report(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Regression: when check_config_files reports unhealthy, the doctor must NOT
        run setup_doctor_runtime / check_models — calling them on a broken config
        either raises PipelexConfigError (discarding the partial check tuples) or
        falls through to "Health check failed unexpectedly" instead of the friendly
        translation. The fix short-circuits to a "skipped — fix configuration errors
        first" model section so the full triage report still reaches stdout.
        """
        mock_setup = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mock_check_models = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.check_models")
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_config_files",
            return_value=(False, 0, "Configuration validation failed: bogus_field is not a valid field"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_telemetry_config",
            return_value=(True, "OK"),
        )
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.check_backend_credentials",
            return_value=(True, {}, "OK"),
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        mock_setup.assert_not_called()
        mock_check_models.assert_not_called()

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["all_healthy"] is False
        # Per-check breakdown still present — the user gets full triage, not just one error line.
        assert parsed["checks"]["config_files"]["healthy"] is False
        assert "bogus_field" in parsed["checks"]["config_files"]["message"]
        assert parsed["checks"]["telemetry"]["healthy"] is True
        assert parsed["checks"]["backend_credentials"]["healthy"] is True
        assert parsed["checks"]["models"]["healthy"] is False
        assert parsed["checks"]["models"]["skipped"] is True
        assert "skipped" in parsed["checks"]["models"]["message"].lower()
        # Config-error recommended action is still emitted.
        assert any("pipelex.toml" in action or "pipelex init config" in action for action in parsed["recommended_actions"])

    def test_pipelex_config_error_from_bootstrap_preserves_partial_report(
        self,
        mocker: MockerFixture,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Regression: a config that passes check_config_files's shape check but fails full
        validation inside setup_doctor_runtime must still produce the full triage envelope.

        Before the fix, the PipelexConfigError arm called agent_error() (NoReturn), which
        discarded the telemetry/backends tuples gathered before the bootstrap and degraded
        the JSON output to a single error payload. The current contract: treat this the
        same as the broken-config short-circuit — mark models as skipped, surface the
        translated message under checks.models, keep every other check in the envelope.
        """
        from pipelex.base_exceptions import PipelexConfigError  # noqa: PLC0415

        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime",
            side_effect=PipelexConfigError("translated validation message"),
        )
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

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        parsed = json.loads(capsys.readouterr().out)
        assert parsed["all_healthy"] is False
        # All non-models sections survive intact.
        assert parsed["checks"]["config_files"]["healthy"] is True
        assert parsed["checks"]["telemetry"]["healthy"] is True
        assert parsed["checks"]["backend_credentials"]["healthy"] is True
        # Models marked as skipped with the translated message inline.
        assert parsed["checks"]["models"]["healthy"] is False
        assert parsed["checks"]["models"]["skipped"] is True
        assert "translated validation message" in parsed["checks"]["models"]["message"]

    def test_bootstrap_pins_console_targets_to_stderr(self, mocker: MockerFixture) -> None:
        """Regression: agent_doctor_cmd must pass AGENT_CLI_STDERR_LOG_FIELDS to setup_doctor_runtime.

        The original bug: agent_doctor_cmd bypassed the agent CLI stdout-hardening that
        every other agent CLI command receives via make_pipelex_for_agent_cli. Doctor's
        check_models internally called log.configure with the user's raw log_config, so a
        user with console_log_target = "stdout" and a raised pipelex log level got log
        lines on stdout before the JSON envelope — breaking json.loads(stdout) for any
        downstream consumer.

        This test asserts that agent_doctor_cmd now folds the stderr overrides into the
        bootstrap call, so log/print targets are pinned before any check can fire, and
        that the defense-in-depth discipline helper is also invoked.
        """
        # Re-mock setup_doctor_runtime and apply_agent_cli_output_discipline so we can
        # capture their call args (the autouse fixture also mocks them, but we need the
        # fresh handles here).
        mock_setup = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mock_discipline = mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.apply_agent_cli_output_discipline")
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

        mock_setup.assert_called_once_with(log_config_overrides=AGENT_CLI_STDERR_LOG_FIELDS, config_dir=None)
        mock_discipline.assert_called()
        # Pin the contract of the field dict itself: both Rich-managed channels must be stderr.
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_log_target"] is ConsoleTarget.STDERR
        assert AGENT_CLI_STDERR_LOG_FIELDS["console_print_target"] is ConsoleTarget.STDERR

    def test_discipline_runs_before_check_models(self, mocker: MockerFixture) -> None:
        """Regression: ``apply_agent_cli_output_discipline`` MUST run before ``check_models``.

        ``setup_doctor_runtime`` calls ``log.configure_if_unset()``, which no-ops when a
        prior process already configured logging (embedded reuse, interleaved test). In
        that case ``AGENT_CLI_STDERR_LOG_FIELDS`` never reaches the handler, and any log
        line ``check_models`` emits can land on stdout — corrupting the JSON envelope.

        Pinning discipline (which mutates the existing handler unconditionally via
        ``log.redirect_to_stderr``) immediately after the bootstrap closes that window
        before any check fires.
        """
        call_order: list[str] = []

        def record_discipline(*_args: object, **_kwargs: object) -> None:
            call_order.append("discipline")

        def record_check_models(*_args: object, **_kwargs: object) -> tuple[bool, str, dict[str, object]]:
            call_order.append("check_models")
            return True, "OK", {}

        mocker.patch("pipelex.cli.agent_cli.commands.doctor_cmd.setup_doctor_runtime")
        mocker.patch(
            "pipelex.cli.agent_cli.commands.doctor_cmd.apply_agent_cli_output_discipline",
            side_effect=record_discipline,
        )
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
            side_effect=record_check_models,
        )

        agent_doctor_cmd(output_format=CliOutputFormat.JSON)

        # discipline must appear before check_models in the call sequence
        assert "discipline" in call_order
        assert "check_models" in call_order
        assert call_order.index("discipline") < call_order.index("check_models")
