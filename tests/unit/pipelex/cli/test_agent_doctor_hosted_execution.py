"""`pipelex-agent doctor` reports where runs execute and, for a hosted setup, judges it by its Pipelex API key."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat
from pipelex.cli.agent_cli.commands.doctor_cmd import agent_doctor_cmd
from pipelex.cli.commands.doctor_cmd import (
    DoctorRuntimeSetup,
    LogSinkCheck,
    PendingMigrationsCheck,
    PendingMigrationsFinding,
    PluginsCheck,
    SecretsProviderCheck,
    TelemetryConfigCheck,
    TelemetryConfigFinding,
)
from pipelex.cogt.model_backends.backend_credentials import BackendCredentialsReport
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture, MockType

TEST_KEY = "plx_sk_test_not_a_secret"
HEALTHY_RUNTIME_SETUP = DoctorRuntimeSetup(
    plugins=PluginsCheck(is_healthy=True, message="Plugins discovered and registered"),
    secrets_provider=SecretsProviderCheck(is_healthy=True, message="Secrets provider 'env' built"),
    log_sink=LogSinkCheck(is_healthy=True, message="Log sink 'console' installed"),
    built_secrets_provider=EnvSecretsProvider(),
)
MISSING_OPENAI = {
    "openai": BackendCredentialsReport(
        backend_name="openai",
        required_vars=["OPENAI_API_KEY"],
        missing_vars=["OPENAI_API_KEY"],
        placeholder_vars=[],
        all_credentials_valid=False,
    ),
}


def _doctor_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    agent_doctor_cmd(output_format=CliOutputFormat.JSON)
    parsed: dict[str, Any] = json.loads(capsys.readouterr().out)
    return parsed


class TestAgentDoctorHostedExecution:
    @pytest.fixture
    def execution(self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MockType:
        """Every row healthy but the two that need provider keys; the returned mock says where runs execute."""
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(tmp_path / "pipelex_home"))
        working_dir = tmp_path / "work"
        working_dir.mkdir()
        monkeypatch.chdir(working_dir)
        isolate_pipelex_api_key(monkeypatch)
        module = "pipelex.cli.agent_cli.commands.doctor_cmd"
        mocker.patch(f"{module}.setup_doctor_runtime", return_value=HEALTHY_RUNTIME_SETUP)
        mocker.patch(f"{module}.apply_agent_cli_output_discipline")
        mocker.patch(f"{module}.silence_logging_for_agent_cli")
        mocker.patch(
            f"{module}.check_pending_migrations",
            return_value=PendingMigrationsCheck(finding=PendingMigrationsFinding.UP_TO_DATE, message="up to date"),
        )
        mocker.patch(f"{module}.check_config_files", return_value=(True, 0, "OK"))
        mocker.patch(
            f"{module}.check_telemetry_config",
            return_value=TelemetryConfigCheck(finding=TelemetryConfigFinding.HEALTHY, message="OK"),
        )
        mocker.patch(f"{module}.check_backend_credentials", return_value=(False, MISSING_OPENAI, "1 backend(s) have missing credentials"))
        mocker.patch(f"{module}.check_models", return_value=(False, "Error checking models: Could not get variable 'OPENAI_API_KEY'", {}))
        return mocker.patch(f"{module}.resolve_doctor_run_execution", return_value=RunExecution.HOSTED)

    @pytest.mark.usefixtures("execution")
    def test_a_hosted_setup_with_a_key_is_healthy_and_says_why(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, TEST_KEY)

        parsed = _doctor_json(capsys)

        assert parsed["all_healthy"] is True
        assert parsed["execution"] == "hosted"
        assert parsed["checks"]["pipelex_api_key"]["healthy"] is True
        assert parsed["checks"]["pipelex_api_key"]["finding"] == "set"
        assert parsed["checks"]["backend_credentials"]["informational"] is True
        assert parsed["checks"]["models"]["informational"] is True
        assert "recommended_actions" not in parsed
        assert TEST_KEY not in json.dumps(parsed)

    @pytest.mark.usefixtures("execution")
    def test_a_hosted_setup_without_a_key_names_pipelex_login(self, capsys: pytest.CaptureFixture[str]) -> None:
        parsed = _doctor_json(capsys)

        assert parsed["all_healthy"] is False
        assert parsed["checks"]["pipelex_api_key"] == {
            "healthy": False,
            "finding": "missing",
            "message": parsed["checks"]["pipelex_api_key"]["message"],
        }
        actions = parsed["recommended_actions"]
        assert any("pipelex login" in action for action in actions)
        assert not any("OPENAI_API_KEY" in action for action in actions)

    def test_a_local_setup_reports_its_execution_and_no_key_row(
        self, execution: MockType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        execution.return_value = RunExecution.LOCAL
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, TEST_KEY)

        parsed = _doctor_json(capsys)

        assert parsed["all_healthy"] is False
        assert parsed["execution"] == "local"
        assert "pipelex_api_key" not in parsed["checks"]
        assert "informational" not in parsed["checks"]["backend_credentials"]
        assert any("OPENAI_API_KEY" in action for action in parsed["recommended_actions"])
