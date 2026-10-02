from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex import log
from pipelex.cogt.model_backends.backend import LEGACY_GATEWAY_MODEL_SPECS_SECTION, PipelexBackend
from pipelex.pipelex import Pipelex
from pipelex.system.pipelex_service.pipelex_service_agreement import (
    PipelexServiceAgreement,
    PipelexServiceOnboarding,
)
from pipelex.system.pipelex_service.pipelex_service_config import PipelexServiceConfig
from pipelex.system.runtime import IntegrationMode, runtime_manager

if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest_mock import MockerFixture

RUNTIME_BOOT_MODULE = "pipelex.runtime_boot"


@pytest.fixture(scope="module", autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: each test boots with its own ``Pipelex.make``."""
    yield
    Pipelex.teardown_if_needed()


@pytest.fixture
def gateway_enabled_boot(mocker: MockerFixture) -> None:
    """A boot with `pipelex_gateway` enabled, the terms accepted, and the session's fresh remote config."""
    mocker.patch(
        f"{RUNTIME_BOOT_MODULE}.enabled_managed_gateway_sections",
        return_value={PipelexBackend.GATEWAY: LEGACY_GATEWAY_MODEL_SPECS_SECTION},
    )
    mocker.patch(
        f"{RUNTIME_BOOT_MODULE}.load_pipelex_service_config_if_exists",
        return_value=PipelexServiceConfig(
            agreement=PipelexServiceAgreement(terms_accepted=True),
            onboarding=PipelexServiceOnboarding(inference_setup_completed=True),
        ),
    )
    mocker.patch(
        "pipelex.system.runtime.RuntimeManager.is_in_codex_cloud",
        new_callable=mocker.PropertyMock,
        return_value=False,
    )


def _boot_and_read_the_stream(*, integration_mode: IntegrationMode) -> bool:
    Pipelex.teardown_if_needed()
    try:
        telemetry_manager = Pipelex.make(integration_mode=integration_mode, needs_inference=True).telemetry_manager
        assert telemetry_manager is not None
        return telemetry_manager.is_pipelex_telemetry_enabled
    finally:
        Pipelex.teardown_if_needed()
        log.reset()


@pytest.mark.usefixtures("gateway_enabled_boot", "gateway_telemetry_reachable")
class TestSetupGatewayTelemetry:
    def test_a_deployment_boot_sends_the_stream(self, mocker: MockerFixture) -> None:
        """The production path, end to end: the one boot that must build the real manager with the Gateway stream on.

        The run mode the shared pytest plugin set is neutralised here, as a deployment has none. Nothing
        else in the suite builds this manager, so a crash in the factory's key lookup or in the
        manager's Gateway branch would otherwise reach every production boot with the Gateway enabled.
        """
        mocker.patch(f"{RUNTIME_BOOT_MODULE}.runtime_manager", is_unit_testing=False)
        assert _boot_and_read_the_stream(integration_mode=IntegrationMode.PYTHON)

    @pytest.mark.parametrize("integration_mode", [IntegrationMode.CI, IntegrationMode.PYTEST])
    def test_a_test_harness_mode_boot_keeps_the_stream_off(self, mocker: MockerFixture, integration_mode: IntegrationMode) -> None:
        """The integration mode alone turns the stream off, as for a harness that boots without the shared pytest plugin."""
        mocker.patch(f"{RUNTIME_BOOT_MODULE}.runtime_manager", is_unit_testing=False)
        assert not _boot_and_read_the_stream(integration_mode=integration_mode)

    def test_a_unit_testing_run_mode_boot_keeps_the_stream_off(self) -> None:
        """The run mode alone turns the stream off: a suite booting in the default `PYTHON` mode, as the shared plugin's recipe does."""
        assert runtime_manager.is_unit_testing, "the shared pytest plugin sets a test run mode for every session that loads it"
        assert not _boot_and_read_the_stream(integration_mode=IntegrationMode.PYTHON)
