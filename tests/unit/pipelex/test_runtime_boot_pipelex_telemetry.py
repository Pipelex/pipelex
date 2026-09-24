import pytest

from pipelex.runtime_boot import RuntimeBoot
from pipelex.runtime_hub import get_telemetry_manager
from pipelex.system.runtime import IntegrationMode

# Spelled out rather than derived from `is_test_harness`, so this table does not lean on the property it
# depends on; `test_integration_mode.py` pins the property itself.
HARNESS_MODES = [IntegrationMode.CI, IntegrationMode.PYTEST]
DEPLOYMENT_MODES = [mode for mode in IntegrationMode if mode not in HARNESS_MODES]


class TestRuntimeBootPipelexTelemetry:
    @pytest.mark.parametrize("integration_mode", DEPLOYMENT_MODES)
    def test_a_deployment_mode_with_every_condition_met_enables_the_stream(self, integration_mode: IntegrationMode) -> None:
        assert RuntimeBoot.should_enable_pipelex_telemetry(
            integration_mode=integration_mode,
            is_gateway_enabled=True,
            needs_inference=True,
            is_gateway_config_cached=False,
        )

    @pytest.mark.parametrize(
        ("is_gateway_enabled", "needs_inference", "is_gateway_config_cached"),
        [
            pytest.param(False, True, False, id="gateway-disabled"),
            pytest.param(True, False, False, id="no-inference"),
            pytest.param(True, True, True, id="cached-config"),
        ],
    )
    def test_each_existing_condition_alone_disables_the_stream(
        self,
        is_gateway_enabled: bool,
        needs_inference: bool,
        is_gateway_config_cached: bool,
    ) -> None:
        assert not RuntimeBoot.should_enable_pipelex_telemetry(
            integration_mode=IntegrationMode.PYTHON,
            is_gateway_enabled=is_gateway_enabled,
            needs_inference=needs_inference,
            is_gateway_config_cached=is_gateway_config_cached,
        )

    @pytest.mark.parametrize("integration_mode", HARNESS_MODES)
    def test_a_test_harness_mode_disables_the_stream_even_with_every_other_condition_met(self, integration_mode: IntegrationMode) -> None:
        """Test runs are not usage, and their fixture user ids must not become persons in the production project.

        Before this condition, every pytest run with `pipelex_gateway` enabled and a fresh remote config
        sent its pipe runs to the Gateway's production analytics project, because the stream's enabling
        condition never read the integration mode.
        """
        assert not RuntimeBoot.should_enable_pipelex_telemetry(
            integration_mode=integration_mode,
            is_gateway_enabled=True,
            needs_inference=True,
            is_gateway_config_cached=False,
        )

    def test_the_suite_boot_has_the_gateway_stream_off(self) -> None:
        """The boot this suite runs under must not send the Gateway stream: the bug's symptom, stated directly.

        This passes trivially on a machine where `pipelex_gateway` is disabled, or where the remote
        config came from the cache, because the stream is off there for those reasons already; the
        table tests above are the precise guard. It asserts on the Gateway stream alone, not on the
        manager being a no-op, because a developer may deliberately allow the custom stream under
        `pytest` in their own `telemetry_allowed_modes`.
        """
        assert not get_telemetry_manager().is_pipelex_telemetry_enabled
