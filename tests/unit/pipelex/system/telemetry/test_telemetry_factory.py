import pytest
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.system.runtime import IntegrationMode, RunMode, runtime_manager
from pipelex.system.telemetry.telemetry_config import TelemetryConfig
from pipelex.system.telemetry.telemetry_factory import TelemetryFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerNoOp
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class TestTelemetryFactoryGatewayDisabledInTestRunMode:
    @pytest.mark.parametrize(
        "test_run_mode",
        [RunMode.UNIT_TEST, RunMode.CI_TEST, RunMode.CODEX_CLOUD_TEST],
    )
    def test_gateway_telemetry_silently_disabled_in_test_run_mode(
        self,
        mocker: MockerFixture,
        test_run_mode: RunMode,
    ) -> None:
        mocker.patch.object(runtime_manager, "_run_mode", test_run_mode)
        secrets_provider = mocker.Mock(spec=SecretsProviderAbstract)
        telemetry_config = TelemetryConfig()

        manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=secrets_provider,
            integration_mode=IntegrationMode.PYTEST,
            remote_config=None,
            is_pipelex_telemetry_enabled=True,
            telemetry_config=telemetry_config,
        )

        assert isinstance(manager, TelemetryManagerNoOp)
        secrets_provider.get_required_secret.assert_not_called()

    def test_gateway_api_key_fetch_attempted_when_run_mode_is_normal(
        self,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch.object(runtime_manager, "_run_mode", RunMode.NORMAL)
        secrets_provider = mocker.Mock(spec=SecretsProviderAbstract)
        secrets_provider.get_required_secret.return_value = "fake_gateway_key"
        telemetry_config = TelemetryConfig()

        # Without test run mode the gateway code path runs. We pass remote_config=None
        # so it raises PipelexUnexpectedError downstream — proving the gateway branch
        # was taken (and therefore that the secret was fetched).
        with pytest.raises(PipelexUnexpectedError):
            TelemetryFactory.make_telemetry_manager(
                secrets_provider=secrets_provider,
                integration_mode=IntegrationMode.CLI,
                remote_config=None,
                is_pipelex_telemetry_enabled=True,
                telemetry_config=telemetry_config,
            )

        secrets_provider.get_required_secret.assert_called_once()
