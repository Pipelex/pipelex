import pytest

from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_config import (
    PipelexGatewayTelemetryConfig,
    PortkeyConfig,
    PostHogConfig,
    PostHogMode,
    TelemetryConfig,
)
from pipelex.system.telemetry.telemetry_manager import TelemetryManager


def _make_manager(*, is_stream_enabled: bool, force_flags: bool) -> TelemetryManager:
    """Assemble a manager whose custom stream is on, as a test run allows, bypassing the constructor's global side effects."""
    telemetry_config = TelemetryConfig(
        custom_posthog=PostHogConfig(mode=PostHogMode.ANONYMOUS, api_key="phc_test"),
        pipelex_gateway=PipelexGatewayTelemetryConfig(
            posthog=PostHogConfig(mode=PostHogMode.OFF),
            portkey=PortkeyConfig(force_debug_enabled=force_flags, force_tracing_enabled=force_flags),
        ),
    )
    manager = TelemetryManager.__new__(TelemetryManager)
    manager.telemetry_config = telemetry_config
    manager._pipelex_telemetry_enabled = is_stream_enabled  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
    return manager


@pytest.fixture
def without_do_not_track(monkeypatch: pytest.MonkeyPatch) -> None:
    """`DO_NOT_TRACK` turns both answers off by itself, which would hide what these tests are about."""
    monkeypatch.delenv(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, raising=False)


@pytest.mark.usefixtures("without_do_not_track")
class TestGatewayPortkeyFollowsStream:
    @pytest.mark.parametrize("force_flags", [True, False])
    def test_backend_debug_does_not_log_while_the_stream_is_off(self, force_flags: bool) -> None:
        """A test run keeps the Gateway stream off, and the backend's `debug` must not reopen Portkey logging behind it."""
        manager = _make_manager(is_stream_enabled=False, force_flags=force_flags)

        assert manager.is_pipelex_gateway_portkey_logging_enabled(is_debug_configured=True) is False

    def test_force_debug_flag_does_not_log_while_the_stream_is_off(self) -> None:
        manager = _make_manager(is_stream_enabled=False, force_flags=True)

        assert manager.is_pipelex_gateway_portkey_logging_enabled(is_debug_configured=False) is False

    def test_force_tracing_flag_does_not_trace_while_the_stream_is_off(self) -> None:
        manager = _make_manager(is_stream_enabled=False, force_flags=True)

        assert manager.is_pipelex_gateway_portkey_tracing_enabled() is False

    def test_the_flags_still_apply_while_the_stream_is_on(self) -> None:
        manager = _make_manager(is_stream_enabled=True, force_flags=True)

        assert manager.is_pipelex_gateway_portkey_logging_enabled(is_debug_configured=False) is True
        assert manager.is_pipelex_gateway_portkey_tracing_enabled() is True

    def test_backend_debug_still_applies_while_the_stream_is_on(self) -> None:
        manager = _make_manager(is_stream_enabled=True, force_flags=False)

        assert manager.is_pipelex_gateway_portkey_logging_enabled(is_debug_configured=True) is True
        assert manager.is_pipelex_gateway_portkey_tracing_enabled() is False
