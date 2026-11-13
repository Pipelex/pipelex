from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from mthds.protocol.problem.registry import CoreCode

from pipelex.errors.problem import ProblemView
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.plugins.discovery import GroupedEntryPoint
from pipelex.plugins.exceptions import UnknownErrorTrackerError
from pipelex.plugins.plugin_group import PluginGroup
from pipelex.system.error_tracking.error_report import ErrorReportKind
from pipelex.system.error_tracking.error_tracking import installed_error_trackers, report_exception
from pipelex.system.error_tracking.error_tracking_config import ErrorTrackerMethod
from pipelex.system.runtime import IntegrationMode, runtime_manager
from pipelex.test_extras.recording_error_tracker import RecordingErrorTracker
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData

if TYPE_CHECKING:
    from collections.abc import Generator
    from importlib.metadata import EntryPoint

    from pytest_mock import MockerFixture

    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
    from pipelex.system.error_tracking.error_tracking_config import ErrorTrackingConfig
    from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract

EXTERNAL_TRACKER_METHOD = "test_tracker"
EXTERNAL_PLUGIN_NAME = "test_error_tracker_ext"

_BUILT_TRACKERS: list[RecordingErrorTracker] = []


def _make_fake_external_tracker(
    _config: ErrorTrackingConfig,
    /,
    *,
    secrets_provider: SecretsProviderAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
    telemetry_manager: TelemetryManagerAbstract,  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
) -> ErrorTrackerAbstract | None:
    tracker = RecordingErrorTracker()
    _BUILT_TRACKERS.append(tracker)
    return tracker


class _FakeErrorTrackerPlugin:
    """An external plugin contributing one error tracker under the ``test_tracker`` token."""

    name = EXTERNAL_PLUGIN_NAME
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: PluginRegistrar) -> None:
        registrar.add_error_tracker(method=EXTERNAL_TRACKER_METHOD, factory=_make_fake_external_tracker)


@pytest.fixture(autouse=True)
def reset_pipelex_config_fixture() -> Generator[None, None, None]:
    """Override the global module fixture: this module boots per test and tears down."""
    Pipelex.teardown_if_needed()
    _BUILT_TRACKERS.clear()
    yield
    Pipelex.teardown_if_needed()


def _test_integration_mode() -> IntegrationMode:
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


@pytest.mark.asyncio(loop_scope="class")
class TestErrorTrackerExternalPlugin:
    async def test_the_tracker_an_external_plugin_registered_receives_operator_faults_and_never_a_caller_s_mistake(
        self, mocker: MockerFixture
    ) -> None:
        """A fake entry point and a config naming its token boot with that tracker installed.

        A run failing on a model only the method names is the method's to fix, `model.unknown` in the `method` domain,
        so it is answered to the caller and not reported; an operator's fault reported through the seam reaches it.
        """
        fake_entry_point = SimpleNamespace(name=EXTERNAL_PLUGIN_NAME, load=lambda: _FakeErrorTrackerPlugin)
        grouped = GroupedEntryPoint(group=PluginGroup.KERNEL, entry_point=cast("EntryPoint", fake_entry_point))
        mocker.patch("pipelex.plugins.discovery._external_entry_points", return_value=[grouped])

        Pipelex.make(
            integration_mode=_test_integration_mode(),
            config_overrides={"runtime": {"error_tracking": {"trackers": [EXTERNAL_TRACKER_METHOD]}}},
        )
        assert len(_BUILT_TRACKERS) == 1
        tracker = _BUILT_TRACKERS[0]
        assert installed_error_trackers() == (tracker,)

        with pytest.raises(PipelineExecutionError) as exc_info:
            await PipelexMTHDSProtocol().execute(
                pipe_code="two_steps", mthds_contents=[LocatedRunFailureTestData.MODEL_MTHDS], inputs={"topic": "cats"}
            )
        assert exc_info.value.to_problem(view=ProblemView.OPERATOR).code == CoreCode.MODEL_UNKNOWN
        assert tracker.reports == []

        try:
            msg = "the host's queue is unreachable"
            raise RuntimeError(msg)
        except RuntimeError as host_fault:
            report_exception(exception=host_fault)

        assert len(tracker.reports) == 1
        report = tracker.reports[0]
        assert report.kind == ErrorReportKind.HANDLED
        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert report.raise_site is not None

        Pipelex.teardown_if_needed()
        assert tracker.is_closed
        assert installed_error_trackers() == ()

    async def test_a_token_nobody_provides_stops_the_boot_naming_the_registered_trackers(self) -> None:
        with pytest.raises(UnknownErrorTrackerError) as exc_info:
            Pipelex.make(
                integration_mode=_test_integration_mode(),
                needs_inference=False,
                config_overrides={"runtime": {"error_tracking": {"trackers": ["nobody_provides_this"]}}},
            )

        assert exc_info.value.method == "nobody_provides_this"
        assert set(exc_info.value.registered_methods) == {method.value for method in ErrorTrackerMethod}
        assert "runtime.error_tracking.trackers" in str(exc_info.value)
        assert installed_error_trackers() == ()
        assert Pipelex.get_optional_instance() is None
