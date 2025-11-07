from contextlib import contextmanager
from typing import Any, Callable, Generator

import posthog
from posthog import Posthog, new_context, tag
from posthog.args import ExceptionArg, OptionalCaptureArgs
from typing_extensions import Unpack, override

from pipelex.system.exceptions import RootException
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty, Setting
from pipelex.system.telemetry.telemetry_config import TelemetryConfig, TelemetryMode
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract
from pipelex.tools.log.log import log
from pipelex.tools.misc.package_utils import get_package_version

DO_NOT_TRACK_ENV_VAR_KEY = "DO_NOT_TRACK"


class TelemetryManager(TelemetryManagerAbstract):
    PRIVACY_NOTICE = "[Privacy: exception message redacted]"

    def __init__(self, telemetry_config: TelemetryConfig):
        self.telemetry_config = telemetry_config

        # Create PostHog client
        self.posthog_client = Posthog(
            project_api_key=self.telemetry_config.project_api_key,
            host=self.telemetry_config.host,
            disable_geoip=not self.telemetry_config.geoip_enabled,
            debug=self.telemetry_config.verbose_enabled,
            on_error=self._handle_transmission_error,
        )

        # Store original capture_exception method
        self._original_capture_exception: Callable[..., Any] = self.posthog_client.capture_exception

        # Wrap capture_exception to sanitize before sending
        self._wrap_capture_exception()

        posthog.privacy_mode = True
        posthog.default_client = self.posthog_client

    def _handle_transmission_error(self, error: Exception | None, _items: list[dict[str, Any]]) -> None:
        """Handle errors that occur during telemetry transmission.

        Args:
            error: The transmission error that occurred
            _items: List of telemetry items that failed to send
        """
        if error:
            log.error(f"Telemetry transmission error: {error}")

    def _wrap_capture_exception(self) -> None:
        """Wrap the PostHog capture_exception method to sanitize exception messages."""

        def sanitized_capture_exception(
            exception: ExceptionArg | None = None,
            **kwargs: Unpack[OptionalCaptureArgs],
        ) -> Any:
            """Capture exception with message sanitization for RootException subclasses."""
            if exception and isinstance(exception, RootException):
                # Create a new exception with sanitized message while preserving the class type
                # Use __new__ to create an instance without calling __init__, which may require extra args
                # This creates a "shell" instance with NO custom attributes (e.g., no tested_concept, wanted_concept, etc.)
                exception_type = type(exception)
                sanitized_exception = exception_type.__new__(exception_type)

                # Set the exception args to our privacy notice
                # This is what str(exception) will return
                sanitized_exception.args = (self.PRIVACY_NOTICE,)

                # Preserve the traceback so we still get stack trace information
                if hasattr(exception, "__traceback__"):
                    sanitized_exception.__traceback__ = exception.__traceback__

                # Note: No custom attributes (tested_concept, wanted_concept, etc.) are present
                # because we used __new__() without calling __init__(). The __dict__ is already empty.

                return self._original_capture_exception(sanitized_exception, **kwargs)
            else:
                # For non-RootException, capture as-is (or auto-detect current exception)
                return self._original_capture_exception(exception, **kwargs)

        # Replace the method
        self.posthog_client.capture_exception = sanitized_capture_exception  # type: ignore[method-assign]

    @override
    def setup(self, integration_mode: IntegrationMode):
        if telemetry_mode := TelemetryManagerAbstract.telemetry_was_just_enabled():
            package_version = get_package_version()
            with new_context():
                tag(name=EventProperty.INTEGRATION, value=integration_mode)
                tag(name=EventProperty.PIPELEX_VERSION, value=package_version)
                tag(name=EventProperty.SETTING, value=Setting.TELEMETRY_MODE)
            self.posthog_client.capture(
                EventName.TELEMETRY_JUST_ENABLED,
                properties={
                    EventProperty.TELEMETRY_MODE: telemetry_mode,
                    EventProperty.PIPELEX_VERSION: package_version,
                },
            )

    @override
    def teardown(self):
        if self.posthog_client:
            try:
                # PostHog client has a shutdown method to flush pending events
                # and close background threads
                self.posthog_client.shutdown()
            except Exception as exc:
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during PostHog shutdown: {exc}")

    @override
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        # We copy the incoming properties to avoid modifying the original dictionary
        # and to convert the keys to str
        # and to remove the properties that are in the redact list
        tracked_properties: dict[str, Any]
        if properties:
            tracked_properties = {key: value for key, value in properties.items() if key not in self.telemetry_config.redact}
        else:
            tracked_properties = {}
        match self.telemetry_config.telemetry_mode:
            case TelemetryMode.ANONYMOUS:
                self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
            case TelemetryMode.IDENTIFIED:
                if not self.telemetry_config.user_id:
                    log.error(f"Could not track event '{event_name}' as identified because user_id is not set, tracking as anonymous")
                    self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
                else:
                    self._track_identified_event(event_name=event_name, properties=tracked_properties, user_id=self.telemetry_config.user_id)
            case TelemetryMode.OFF:
                log.verbose(f"Telemetry is off, skipping event '{event_name}'")

    def _track_anonymous_event(self, event_name: str, properties: dict[str, Any]):
        if not self.posthog_client:
            return
        if self.telemetry_config.dry_mode_enabled:
            if properties:
                log.debug(properties, title=f"Tracking anonymous event '{event_name}'. Properties")
            else:
                log.debug(f"Tracking anonymous event '{event_name}'. No properties.")
        else:
            properties["$process_person_profile"] = False
            self.posthog_client.capture(event_name, properties=properties)
            log.verbose(f"Tracked anonymous event '{event_name}' with properties: {properties}")

    def _track_identified_event(self, event_name: str, properties: dict[str, Any], user_id: str):
        if not self.posthog_client:
            return
        if self.telemetry_config.dry_mode_enabled:
            if properties:
                log.debug(properties, title=f"Tracking identified event '{event_name}'. Properties")
            else:
                log.debug(f"Tracking identified event '{event_name}'. No properties.")
        else:
            self.posthog_client.capture(event_name, distinct_id=user_id, properties=properties)
            log.verbose(f"Tracked identified event '{event_name}' with properties: {properties}")

    @override
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """Context manager that uses PostHog's new_context when telemetry is enabled."""
        with new_context():
            yield
