from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import build_registrar
from pipelex.plugins.error_tracker_registry import ErrorTrackerRegistry
from pipelex.plugins.exceptions import DuplicateErrorTrackerError, UnknownErrorTrackerError
from pipelex.plugins.registrar import PluginOrigin, PluginRegistrar
from pipelex.providers.builtins import KERNEL_BUILTIN_PLUGINS, KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES, KERNEL_ENTRY_POINT_GROUPS
from pipelex.system.error_tracking.error_tracking_config import ErrorTrackerMethod, ErrorTrackingConfig
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerNoOp
from pipelex.test_extras.recording_error_tracker import RecordingErrorTracker
from pipelex.tools.secrets.env_secrets_provider import EnvSecretsProvider

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.plugins.error_tracker_registry import ErrorTrackerFactoryFn
    from pipelex.system.configuration.configs import PipelexConfig
    from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
    from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

_RECORDER = RecordingErrorTracker()


def _fake_config() -> PipelexConfig:
    return cast("PipelexConfig", SimpleNamespace(runtime=SimpleNamespace(plugins=SimpleNamespace(disabled=[]))))


def _recording_factory(
    _config: ErrorTrackingConfig,
    /,
    *,
    secrets_provider: SecretsProviderAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
    telemetry_manager: TelemetryManagerAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
) -> ErrorTrackerAbstract | None:
    return _RECORDER


def _unconfigured_factory(
    _config: ErrorTrackingConfig,
    /,
    *,
    secrets_provider: SecretsProviderAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
    telemetry_manager: TelemetryManagerAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
) -> ErrorTrackerAbstract | None:
    """A tracker whose destination this process does not configure, a DSN left unset for instance."""
    return None


def _registrar_with(*, factories: dict[str, object]) -> PluginRegistrar:
    registrar = PluginRegistrar(config=_fake_config())
    registrar.begin_plugin(name="alpha", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)
    for method, factory in factories.items():
        registrar.add_error_tracker(method=method, factory=cast("ErrorTrackerFactoryFn", factory))
    return registrar


class TestErrorTrackerRegistry:
    def test_a_registered_factory_is_retrievable_and_recorded_as_a_contribution(self) -> None:
        registrar = _registrar_with(factories={"sentry": _recording_factory})

        registry = ErrorTrackerRegistry(registrar.error_trackers)

        assert registry.get_required(method="sentry") is _recording_factory
        assert registry.methods == ["sentry"]
        assert "error tracker sentry" in registrar.discoveries[0].contributions

    def test_a_duplicate_method_fails_loud_naming_both_plugins(self) -> None:
        registrar = _registrar_with(factories={"sentry": _recording_factory})
        registrar.begin_plugin(name="beta", origin=PluginOrigin.EXTERNAL, targets_api=PLUGIN_API_VERSION, group=None)

        with pytest.raises(DuplicateErrorTrackerError) as exc_info:
            registrar.add_error_tracker(method="sentry", factory=_recording_factory)

        assert (exc_info.value.first_plugin, exc_info.value.second_plugin, exc_info.value.method) == ("alpha", "beta", "sentry")

    def test_the_configured_trackers_are_built_in_order_leaving_out_one_with_nothing_to_report_to(self) -> None:
        registry = ErrorTrackerRegistry(_registrar_with(factories={"sentry": _recording_factory, "absent": _unconfigured_factory}).error_trackers)

        trackers = registry.make_error_trackers(
            config=ErrorTrackingConfig(trackers=["absent", "sentry"]),
            secrets_provider=EnvSecretsProvider(),
            telemetry_manager=TelemetryManagerNoOp(),
        )

        assert trackers == [_RECORDER]

    def test_a_token_nobody_registered_stops_before_any_factory_runs(self, mocker: MockerFixture) -> None:
        factory = mocker.MagicMock(return_value=_RECORDER)
        registry = ErrorTrackerRegistry(_registrar_with(factories={"sentry": factory}).error_trackers)

        with pytest.raises(UnknownErrorTrackerError) as exc_info:
            registry.make_error_trackers(
                config=ErrorTrackingConfig(trackers=["sentry", "nobody_provides_this"]),
                secrets_provider=EnvSecretsProvider(),
                telemetry_manager=TelemetryManagerNoOp(),
            )

        factory.assert_not_called()
        assert exc_info.value.registered_methods == ["sentry"]
        assert "runtime.error_tracking.trackers" in str(exc_info.value)

    def test_a_factory_that_raises_closes_the_trackers_built_before_it(self, mocker: MockerFixture) -> None:
        built_first = RecordingErrorTracker()
        built_second = RecordingErrorTracker()
        close_second = mocker.patch.object(built_second, "close", side_effect=RuntimeError("the tracker could not flush"))
        built_third = RecordingErrorTracker()
        failing_factory = mocker.MagicMock(side_effect=RuntimeError("the SDK could not start"))
        registry = ErrorTrackerRegistry(
            _registrar_with(
                factories={
                    "first": mocker.MagicMock(return_value=built_first),
                    "second": mocker.MagicMock(return_value=built_second),
                    "broken": failing_factory,
                    "third": mocker.MagicMock(return_value=built_third),
                }
            ).error_trackers
        )

        with pytest.raises(RuntimeError, match="the SDK could not start"):
            registry.make_error_trackers(
                config=ErrorTrackingConfig(trackers=["first", "second", "broken", "third"]),
                secrets_provider=EnvSecretsProvider(),
                telemetry_manager=TelemetryManagerNoOp(),
            )

        assert built_first.is_closed
        # A tracker that cannot close does not stop the others closing, nor replace the boot's error.
        close_second.assert_called_once_with()
        assert not built_third.is_closed

    def test_a_tracker_named_twice_is_refused_by_the_configuration(self) -> None:
        with pytest.raises(ValueError, match="more than once: sentry"):
            ErrorTrackingConfig(trackers=["sentry", "posthog", "sentry"])

    def test_the_builtin_plugin_contributes_the_posthog_tracker_which_reports_nothing_without_a_stream(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[])
        registrar = build_registrar(
            config=_fake_config(),
            boot_orchestrator=None,
            builtin_plugins=KERNEL_BUILTIN_PLUGINS,
            core_unconditional_plugin_names=KERNEL_CORE_UNCONDITIONAL_PLUGIN_NAMES,
            entry_point_groups=KERNEL_ENTRY_POINT_GROUPS,
        )
        registry = ErrorTrackerRegistry(registrar.error_trackers)

        by_name = {discovery.name: discovery for discovery in registrar.discoveries}
        assert by_name["error_trackers"].contributions == [f"error tracker {ErrorTrackerMethod.POSTHOG}"]
        assert (
            registry.make_error_trackers(
                config=ErrorTrackingConfig(trackers=[ErrorTrackerMethod.POSTHOG]),
                secrets_provider=EnvSecretsProvider(),
                telemetry_manager=TelemetryManagerNoOp(),
            )
            == []
        )
