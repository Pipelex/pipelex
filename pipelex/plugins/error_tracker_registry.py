from typing import Protocol

from pipelex.plugins.exceptions import UnknownErrorTrackerError
from pipelex.system.error_tracking.error_tracker import ErrorTrackerAbstract
from pipelex.system.error_tracking.error_tracking_config import ErrorTrackingConfig
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.secrets.secrets_provider_abstract import SecretsProviderAbstract


class ErrorTrackerFactoryFn(Protocol):
    """A plugin's factory for one error tracker: the error-tracking config and the boot's providers in, a tracker or nothing out.

    Called once at boot, after the telemetry manager is built, for each token ``runtime.error_tracking.trackers``
    names, never at registration, so a factory may import its SDK and initialise its client while ``register`` stays
    import-light. It returns ``None`` when its destination is not configured in this process, a tracker whose DSN or
    key is absent for instance: the boot goes on with no tracker of that kind, rather than failing a process the
    operator chose not to report from.

    The secrets provider is the way a factory reads a credential, a ``${…}`` placeholder through ``substitute_vars``
    included. The telemetry manager is the one this boot built, which the built-in ``posthog`` tracker reports through,
    since it holds the operator's PostHog client; a tracker of another kind ignores it. ``config`` is positional-only
    so that an implementation may spell its own first parameter as it likes.
    """

    def __call__(
        self,
        config: ErrorTrackingConfig,
        /,
        *,
        secrets_provider: SecretsProviderAbstract,
        telemetry_manager: TelemetryManagerAbstract,
    ) -> ErrorTrackerAbstract | None: ...


class ErrorTrackerRegistry:
    """Read view over the error-tracker factories contributed by discovered plugins.

    Keyed by the open tracker ``method`` token (a ``str``; the built-in ``ErrorTrackerPlugin`` registers ``posthog``, an
    external plugin registers e.g. ``"sentry"``). Built once at boot from the registrar's accumulated
    ``error_trackers``; boot calls the factory of each token ``runtime.error_tracking.trackers`` names. Mirrors
    ``LogSinkRegistry``, except that a process may install several trackers where it installs one sink.
    """

    def __init__(self, error_trackers: dict[str, ErrorTrackerFactoryFn]):
        self._error_trackers: dict[str, ErrorTrackerFactoryFn] = dict(error_trackers)

    def get_required(self, *, method: str) -> ErrorTrackerFactoryFn:
        factory = self._error_trackers.get(method)
        if factory is None:
            raise UnknownErrorTrackerError(method=method, registered_methods=self.methods)
        return factory

    def has(self, *, method: str) -> bool:
        return method in self._error_trackers

    @property
    def methods(self) -> list[str]:
        return list(self._error_trackers)

    def make_error_trackers(
        self,
        *,
        config: ErrorTrackingConfig,
        secrets_provider: SecretsProviderAbstract,
        telemetry_manager: TelemetryManagerAbstract,
    ) -> list[ErrorTrackerAbstract]:
        """Build the trackers ``config`` names, in its order, leaving out each one whose factory found nothing to report to.

        Every token is looked up before any factory runs, so a token nobody registered stops the boot before a tracker
        initialises its SDK.
        """
        factories = [self.get_required(method=method) for method in config.trackers]
        trackers: list[ErrorTrackerAbstract] = []
        for factory in factories:
            tracker = factory(config, secrets_provider=secrets_provider, telemetry_manager=telemetry_manager)
            if tracker is not None:
                trackers.append(tracker)
        return trackers
