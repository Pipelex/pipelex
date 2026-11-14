from typing import TYPE_CHECKING

from pipelex.plugins.contract import PLUGIN_API_VERSION
from pipelex.system.error_tracking.error_tracking_config import ErrorTrackerMethod, ErrorTrackingConfig

if TYPE_CHECKING:
    from pipelex.plugins.registrar import PluginRegistrar
    from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
    from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
    from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


def _make_posthog_error_tracker(
    _config: ErrorTrackingConfig,
    /,
    *,
    secrets_provider: "SecretsProviderAbstract",  # ruff: ignore[unused-function-argument] - the ErrorTrackerFactoryFn shape
    telemetry_manager: "TelemetryManagerAbstract",
) -> "ErrorTrackerAbstract | None":
    """The operator's PostHog stream as an error tracker, or ``None`` when this process has none.

    The stream is the one ``telemetry.toml`` configures under ``[custom_posthog]``: no tracker when it is off, when the
    integration mode does not allow it or when ``DO_NOT_TRACK`` is set, exactly as for every other capture on it.
    """
    return telemetry_manager.make_error_tracker()


class ErrorTrackerPlugin:
    """Built-in provider of the ``posthog`` error tracker.

    Not core-unconditional: a process may report its errors nowhere, and one that disables this plugin while
    ``runtime.error_tracking.trackers`` still names ``posthog`` stops at boot naming the registered trackers. Importing
    this module is import-light: the PostHog client is the telemetry manager's, built before the factory runs.
    """

    name = "error_trackers"
    targets_api = PLUGIN_API_VERSION

    def register(self, registrar: "PluginRegistrar") -> None:
        registrar.add_error_tracker(method=ErrorTrackerMethod.POSTHOG, factory=_make_posthog_error_tracker)
