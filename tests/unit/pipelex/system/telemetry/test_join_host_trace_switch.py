from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.exceptions import TelemetryConfigValidationError
from pipelex.system.telemetry.otel_constants import OTelConstants
from pipelex.system.telemetry.telemetry_config import (
    LangfuseConfig,
    OtlpExporterConfig,
    PostHogConfig,
    PostHogMode,
    PostHogTracingConfig,
    TelemetryConfig,
)
from pipelex.system.telemetry.telemetry_factory import JOIN_HOST_TRACE_SETTING, TelemetryFactory
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerNoOp
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_SENTRY_LIKE_OTLP = OtlpExporterConfig(
    name="errors",
    endpoint="https://ingest.example.test/api/1/integration/otlp/v1/traces",
    headers={"x-sentry-auth": "sentry sentry_key=public-key-for-tests"},
)


def _config(
    *,
    join_host_trace: bool = False,
    mode: PostHogMode = PostHogMode.IDENTIFIED,
    tracing_enabled: bool = True,
    otlp: list[OtlpExporterConfig] | None = None,
    langfuse_enabled: bool = False,
) -> TelemetryConfig:
    return TelemetryConfig(
        join_host_trace=join_host_trace,
        custom_posthog=PostHogConfig(mode=mode, user_id="operator", api_key="phc_test", tracing=PostHogTracingConfig(enabled=tracing_enabled)),
        otlp=otlp or [],
        langfuse=LangfuseConfig(enabled=langfuse_enabled),
        telemetry_allowed_modes={"fastapi": True, "pytest": False},
    )


class TestJoinHostTraceSwitch:
    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY, raising=False)
        monkeypatch.delenv(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, raising=False)

    @pytest.mark.parametrize(
        ("in_code", "env_value", "in_file", "expected"),
        [
            (None, None, False, False),
            (None, None, True, True),
            (None, "true", False, True),
            (None, "TRUE", False, True),
            (None, "1", False, True),
            (None, "false", True, False),
            (None, "0", True, False),
            (None, "", True, True),
            (True, "false", False, True),
            (False, "true", True, False),
        ],
    )
    def test_code_wins_over_the_environment_which_wins_over_the_file(
        self, monkeypatch: pytest.MonkeyPatch, in_code: bool | None, env_value: str | None, in_file: bool, expected: bool
    ) -> None:
        if env_value is not None:
            monkeypatch.setenv(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY, env_value)

        resolved = TelemetryFactory.resolve_join_host_trace(telemetry_config=_config(join_host_trace=in_file), join_host_trace=in_code)

        assert resolved is expected

    def test_an_unreadable_environment_value_refuses_the_boot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY, "yes")

        with pytest.raises(TelemetryConfigValidationError, match=OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY) as exc_info:
            TelemetryFactory.resolve_join_host_trace(telemetry_config=_config(), join_host_trace=None)

        assert exc_info.value.setting == OTelConstants.JOIN_HOST_TRACE_ENV_VAR_KEY

    @pytest.mark.parametrize(
        ("telemetry_config", "expected"),
        [
            (_config(mode=PostHogMode.OFF), []),
            (_config(tracing_enabled=False, otlp=[_SENTRY_LIKE_OTLP], langfuse_enabled=True), []),
            (_config(), ["custom_posthog"]),
            (_config(otlp=[_SENTRY_LIKE_OTLP], langfuse_enabled=True), ["custom_posthog", "otlp:errors", "langfuse"]),
        ],
    )
    def test_the_span_destinations_are_those_the_tracer_feeds(self, telemetry_config: TelemetryConfig, expected: list[str]) -> None:
        assert telemetry_config.operator_span_destinations() == expected

    @pytest.mark.parametrize(
        "telemetry_config",
        [
            _config(join_host_trace=True, mode=PostHogMode.OFF, otlp=[_SENTRY_LIKE_OTLP]),
            _config(join_host_trace=True, tracing_enabled=False, otlp=[_SENTRY_LIKE_OTLP]),
        ],
    )
    def test_the_switch_with_no_span_destination_refuses_the_boot(self, mocker: MockerFixture, telemetry_config: TelemetryConfig) -> None:
        telemetry_manager_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.TelemetryManager")

        with pytest.raises(TelemetryConfigValidationError, match="join_host_trace is on, but no destination") as exc_info:
            TelemetryFactory.make_telemetry_manager(
                secrets_provider=EnvSecretsProvider(),
                integration_mode=IntegrationMode.FASTAPI,
                telemetry_config=telemetry_config,
            )

        assert exc_info.value.setting == JOIN_HOST_TRACE_SETTING
        telemetry_manager_class.assert_not_called()

    def test_the_switch_from_code_is_refused_the_same_way(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.system.telemetry.telemetry_manager.TelemetryManager")

        with pytest.raises(TelemetryConfigValidationError, match="join_host_trace is on"):
            TelemetryFactory.make_telemetry_manager(
                secrets_provider=EnvSecretsProvider(),
                integration_mode=IntegrationMode.FASTAPI,
                telemetry_config=_config(mode=PostHogMode.OFF),
                join_host_trace=True,
            )

    def test_the_switch_with_a_span_destination_reaches_the_manager(self, mocker: MockerFixture) -> None:
        telemetry_manager_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.TelemetryManager")
        telemetry_config = _config(join_host_trace=True, otlp=[_SENTRY_LIKE_OTLP])

        TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=IntegrationMode.FASTAPI,
            telemetry_config=telemetry_config,
        )

        telemetry_manager_class.assert_called_once_with(telemetry_config=telemetry_config, join_host_trace=True)

    def test_the_switch_off_is_passed_on_as_off(self, mocker: MockerFixture) -> None:
        telemetry_manager_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.TelemetryManager")
        telemetry_config = _config()

        TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=IntegrationMode.FASTAPI,
            telemetry_config=telemetry_config,
        )

        telemetry_manager_class.assert_called_once_with(telemetry_config=telemetry_config, join_host_trace=False)

    @pytest.mark.parametrize("is_do_not_track", [True, False])
    def test_with_telemetry_off_as_a_whole_the_switch_is_inert(
        self, mocker: MockerFixture, monkeypatch: pytest.MonkeyPatch, is_do_not_track: bool
    ) -> None:
        """``DO_NOT_TRACK`` or a disallowed integration mode starts no span, so nothing could be orphaned and nothing is refused."""
        telemetry_manager_class = mocker.patch("pipelex.system.telemetry.telemetry_manager.TelemetryManager")
        integration_mode = IntegrationMode.FASTAPI
        if is_do_not_track:
            monkeypatch.setenv(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY, "1")
        else:
            integration_mode = IntegrationMode.PYTEST

        telemetry_manager = TelemetryFactory.make_telemetry_manager(
            secrets_provider=EnvSecretsProvider(),
            integration_mode=integration_mode,
            telemetry_config=_config(join_host_trace=True, mode=PostHogMode.OFF),
        )

        assert isinstance(telemetry_manager, TelemetryManagerNoOp)
        assert telemetry_manager.join_host_trace is False
        telemetry_manager_class.assert_not_called()
