"""`pipelex doctor` judges a hosted setup by its Pipelex API key, and reports provider credentials as for `--local` runs only."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from rich.console import Console

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.commands.doctor_cmd import (
    DoctorRuntimeSetup,
    LogSinkCheck,
    PendingMigrationsCheck,
    PendingMigrationsFinding,
    PluginsCheck,
    SecretsProviderCheck,
    TelemetryConfigCheck,
    TelemetryConfigFinding,
    do_doctor_cmd,
    resolve_doctor_run_execution,
)
from pipelex.cogt.model_backends.backend_credentials import BackendCredentialsReport
from pipelex.cogt.models.deck_manifest import DeckSyncReport
from pipelex.hosted.client_factory import PIPELEX_API_KEY_ENV_KEY
from pipelex.hosted.run_config import RunExecution
from pipelex.system.environment import PIPELEX_HOME_ENV_KEY
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider
from tests.helpers.pipelex_api_key_env import isolate_pipelex_api_key

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

TEST_KEY = "plx_sk_test_not_a_secret"
HEALTHY_RUNTIME_SETUP = DoctorRuntimeSetup(
    plugins=PluginsCheck(is_healthy=True, message="Plugins discovered and registered"),
    secrets_provider=SecretsProviderCheck(is_healthy=True, message="Secrets provider 'env' built"),
    log_sink=LogSinkCheck(is_healthy=True, message="Log sink 'console' installed"),
    built_secrets_provider=EnvSecretsProvider(),
)
CLEAN_DECK = DeckSyncReport(kit_version="1.2.0", installed_kit_version="1.2.0", manifest_present=True, files={})
MISSING_OPENAI = {
    "openai": BackendCredentialsReport(
        backend_name="openai",
        required_vars=["OPENAI_API_KEY"],
        missing_vars=["OPENAI_API_KEY"],
        placeholder_vars=[],
        all_credentials_valid=False,
    ),
}
MODELS_NEED_A_PROVIDER_KEY = "Error checking models: Could not get variable 'OPENAI_API_KEY'"


def _run_doctor(*, fix: bool = False) -> int | str | None:
    with pytest.raises(SystemExit) as exc_info:
        do_doctor_cmd(fix=fix)
    return exc_info.value.code


class TestDoctorHostedExecution:
    @pytest.fixture
    def doctor_mocks(self, mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
        """Every row healthy but the two that need provider keys, which a hosted setup does not have."""
        monkeypatch.setenv(PIPELEX_HOME_ENV_KEY, str(tmp_path / "pipelex_home"))
        working_dir = tmp_path / "work"
        working_dir.mkdir()
        monkeypatch.chdir(working_dir)
        isolate_pipelex_api_key(monkeypatch)
        mocks: dict[str, Any] = {
            "setup": mocker.patch("pipelex.cli.commands.doctor_cmd.setup_doctor_runtime", return_value=HEALTHY_RUNTIME_SETUP),
            "config": mocker.patch("pipelex.cli.commands.doctor_cmd.check_config_files", return_value=(True, 0, "OK")),
            "telemetry": mocker.patch(
                "pipelex.cli.commands.doctor_cmd.check_telemetry_config",
                return_value=TelemetryConfigCheck(finding=TelemetryConfigFinding.HEALTHY, message="OK"),
            ),
            "migrations": mocker.patch(
                "pipelex.cli.commands.doctor_cmd.check_pending_migrations",
                return_value=PendingMigrationsCheck(finding=PendingMigrationsFinding.UP_TO_DATE, message="up to date"),
            ),
            "backends": mocker.patch(
                "pipelex.cli.commands.doctor_cmd.check_backend_credentials",
                return_value=(False, MISSING_OPENAI, "1 backend(s) have missing or invalid credentials"),
            ),
            "models": mocker.patch("pipelex.cli.commands.doctor_cmd.check_models", return_value=(False, MODELS_NEED_A_PROVIDER_KEY, {})),
            "deck": mocker.patch("pipelex.cli.commands.doctor_cmd.check_deck_sync", return_value=(True, CLEAN_DECK, "OK")),
            "internal_backend": mocker.patch("pipelex.cli.commands.doctor_cmd.check_internal_backend_sync", return_value=(True, CLEAN_DECK, "OK")),
            "execution": mocker.patch("pipelex.cli.commands.doctor_cmd.resolve_doctor_run_execution", return_value=RunExecution.HOSTED),
            "init_cmd": mocker.patch("pipelex.cli.commands.doctor_cmd.init_cmd"),
            "confirm": mocker.patch("pipelex.cli.commands.doctor_cmd.Confirm.ask", return_value=True),
        }
        recorded_console = Console(width=200, record=True, color_system=None)
        mocker.patch("pipelex.cli.commands.doctor_cmd.get_console", return_value=recorded_console)
        mocks["console"] = recorded_console
        return mocks

    def test_a_hosted_setup_with_a_key_is_healthy_without_provider_keys(self, doctor_mocks: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, TEST_KEY)

        assert _run_doctor() == 0

        output = doctor_mocks["console"].export_text()
        assert "All systems healthy" in output
        assert "Manual Fixes Required" not in output
        assert "Set the following environment variables" not in output
        assert "--local" in output
        assert "Pipelex API Key" in output
        assert TEST_KEY not in output

    def test_a_hosted_setup_without_a_key_fails_naming_pipelex_login(self, doctor_mocks: dict[str, Any]) -> None:
        assert _run_doctor() == 1

        output = doctor_mocks["console"].export_text()
        assert "pipelex login" in output
        assert "Set the following environment variables" not in output
        assert "OPENAI_API_KEY=" not in output

    def test_a_hosted_setup_with_a_value_that_is_not_a_pipelex_key_fails(self, doctor_mocks: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, "sk-not-a-pipelex-key")

        assert _run_doctor() == 1

        output = doctor_mocks["console"].export_text()
        assert "pipelex login" in output
        assert "sk-not-a-pipelex-key" not in output

    def test_fix_mode_on_a_hosted_setup_with_a_key_has_nothing_to_fix(self, doctor_mocks: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, TEST_KEY)

        assert _run_doctor(fix=True) == 0

        doctor_mocks["init_cmd"].assert_not_called()

    def test_a_local_setup_still_needs_its_provider_keys(self, doctor_mocks: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
        doctor_mocks["execution"].return_value = RunExecution.LOCAL
        monkeypatch.setenv(PIPELEX_API_KEY_ENV_KEY, TEST_KEY)

        assert _run_doctor() == 1

        output = doctor_mocks["console"].export_text()
        assert "Set the following environment variables" in output
        assert "Pipelex API Key" not in output

    def test_a_configuration_that_does_not_load_is_judged_as_local(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.commands.doctor_cmd.configured_run_execution", side_effect=PipelexConfigError("broken"))

        assert resolve_doctor_run_execution() == RunExecution.LOCAL

    def test_the_configured_execution_is_the_one_judged(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cli.commands.doctor_cmd.configured_run_execution", return_value=RunExecution.HOSTED)

        assert resolve_doctor_run_execution() == RunExecution.HOSTED
