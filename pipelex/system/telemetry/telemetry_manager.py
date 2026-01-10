from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

import posthog
from opentelemetry.trace import Tracer as OTelTracer
from posthog import Posthog, new_context  # type: ignore[attr-defined]
from posthog.args import ExceptionArg, OptionalCaptureArgs
from typing_extensions import Unpack, override

from pipelex import log
from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.exceptions import PipelexError
from pipelex.system.pipelex_service.pipelex_details import PipelexDetails
from pipelex.system.pipelex_service.remote_config import RemoteConfig
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.otel_constants import OTelConstants, PostHogAttr, PostHogEvent
from pipelex.system.telemetry.otel_factory import OtelFactory
from pipelex.system.telemetry.telemetry_config import PostHogMode, TelemetryConfig, TelemetryRedactionConfig
from pipelex.system.telemetry.telemetry_manager_abstract import TelemetryManagerAbstract

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider as OTelTracerProvider


class TelemetryManager(TelemetryManagerAbstract):
    PRIVACY_NOTICE = "[Privacy: exception message redacted]"

    def __init__(
        self,
        telemetry_config: TelemetryConfig,
        remote_config: RemoteConfig | None,
        pipelex_telemetry_enabled: bool = False,
        gateway_api_key: str | None = None,
    ):
        """Initialize the TelemetryManager with custom and optional Pipelex telemetry.

        Args:
            telemetry_config: User's telemetry configuration.
            remote_config: Remote configuration for Pipelex Service (including telemetry).
            pipelex_telemetry_enabled: Whether Pipelex internal telemetry is enabled (for gateway).
            gateway_api_key: The user's Pipelex Gateway API key (required if pipelex_telemetry_enabled).
        """
        self.telemetry_config = telemetry_config
        self._pipelex_telemetry_enabled = pipelex_telemetry_enabled
        self._pipelex_distinct_id: str | None = None

        # Create custom PostHog client only if user's telemetry is enabled
        self.custom_posthog_client: Posthog | None = None
        if telemetry_config.custom_posthog.mode.is_enabled:
            if not telemetry_config.custom_posthog.api_key:
                msg = "Custom PostHog API key is not set"
                raise PipelexUnexpectedError(msg)
            self.custom_posthog_client = Posthog(
                project_api_key=telemetry_config.custom_posthog.api_key,
                host=telemetry_config.custom_posthog.endpoint,
                disable_geoip=not telemetry_config.custom_posthog.geoip,
                debug=telemetry_config.custom_posthog.debug,
                on_error=self._handle_transmission_error,
            )

        # Create Pipelex PostHog client if gateway telemetry is enabled
        self.pipelex_posthog_client: Posthog | None = None
        if pipelex_telemetry_enabled:
            if gateway_api_key:
                self._pipelex_distinct_id = PipelexDetails.make_distinct_id(gateway_api_key)
            if not remote_config:
                msg = "Pipelex Gateway telemetry is enabled but remote config is not set"
                raise PipelexUnexpectedError(msg)
            pipelex_posthog_config = remote_config.posthog
            self.pipelex_posthog_client = Posthog(
                project_api_key=pipelex_posthog_config.project_api_key,
                host=pipelex_posthog_config.endpoint,
                disable_geoip=not pipelex_posthog_config.is_geoip_enabled,
                debug=pipelex_posthog_config.is_debug_enabled,
                on_error=self._handle_pipelex_transmission_error,
            )
            log.verbose("Pipelex Gateway telemetry enabled")

        # Create OTel tracer for AI tracing if enabled
        self._otel_tracer: OTelTracer | None
        self._tracer_provider: OTelTracerProvider | None
        if telemetry_config.custom_posthog.tracing.enabled or pipelex_telemetry_enabled:
            # AI tracing is enabled if either custom or pipelex telemetry wants it
            # Create redaction config from user settings for custom telemetry
            custom_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(posthog_config=telemetry_config.custom_posthog)
            if telemetry_config.pipelex_gateway:
                pipelex_gateway_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(
                    posthog_config=telemetry_config.pipelex_gateway.posthog
                )
            else:
                pipelex_gateway_redaction_config = TelemetryRedactionConfig.make_from_posthog_config(posthog_config=None)
            self._otel_tracer, self._tracer_provider = OtelFactory.make_ai_tracer(
                user_id=telemetry_config.custom_posthog.user_id,
                custom_posthog_client=self.custom_posthog_client if telemetry_config.custom_posthog.tracing.enabled else None,
                custom_redaction_config=custom_redaction_config,
                pipelex_posthog_client=self.pipelex_posthog_client,
                pipelex_gateway_redaction_config=pipelex_gateway_redaction_config,
                pipelex_distinct_id=self._pipelex_distinct_id,
                otlp_exporters=telemetry_config.otlp,
                langfuse_config=telemetry_config.langfuse,
            )
            log.verbose("AI tracing enabled: OpenTelemetry tracer created")
        else:
            self._otel_tracer = None
            self._tracer_provider = None
            log.verbose("AI tracing disabled: No OpenTelemetry tracer created")

        # Wrap capture_exception to sanitize before sending (for whichever clients are enabled)
        if self.custom_posthog_client:
            self._wrap_capture_exception(self.custom_posthog_client)
        if self.pipelex_posthog_client:
            self._wrap_capture_exception(self.pipelex_posthog_client)

        # Set global PostHog settings (prefer custom client, fall back to pipelex client)
        posthog.privacy_mode = True
        posthog.default_client = self.custom_posthog_client or self.pipelex_posthog_client

    def _handle_transmission_error(self, error: Exception | None, _items: list[dict[str, Any]]) -> None:
        """Handle errors that occur during custom telemetry transmission.

        Args:
            error: The transmission error that occurred
            _items: List of telemetry items that failed to send
        """
        if error:
            log.error(f"Telemetry transmission error: {error}")

    def _handle_pipelex_transmission_error(self, error: Exception | None, _items: list[dict[str, Any]]) -> None:
        """Handle errors that occur during Pipelex telemetry transmission.

        Args:
            error: The transmission error that occurred
            _items: List of telemetry items that failed to send
        """
        if error:
            log.debug(f"Pipelex telemetry transmission error: {error}")

    def _wrap_capture_exception(self, client: Posthog) -> None:
        """Wrap a PostHog client's capture_exception method to sanitize exception messages.

        Args:
            client: The PostHog client to wrap.
        """
        original_capture_exception = client.capture_exception

        def sanitized_capture_exception(
            exception: ExceptionArg | None = None,
            **kwargs: Unpack[OptionalCaptureArgs],
        ) -> Any:
            """Capture exception with message sanitization for PipelexError subclasses."""
            if exception and isinstance(exception, PipelexError):
                # Create a new exception with sanitized message while preserving the class type
                # Use __new__ to create an instance without calling __init__, which may require extra args
                # This creates a "shell" instance with NO custom attributes
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

                return original_capture_exception(sanitized_exception, **kwargs)
            else:
                # For non-PipelexError, capture as-is (or auto-detect current exception)
                return original_capture_exception(exception, **kwargs)

        client.capture_exception = sanitized_capture_exception  # type: ignore[method-assign]

    @override
    def setup(self, integration_mode: IntegrationMode):
        pass

    @override
    def teardown(self):
        # First, shutdown the TracerProvider to flush all pending spans
        # This MUST happen before PostHog shutdown, otherwise spans won't be exported
        if self._tracer_provider:
            try:
                log.verbose("Shutting down OTel TracerProvider (flushing pending spans)...")
                self._tracer_provider.shutdown()
                log.verbose("OTel TracerProvider shutdown complete")
            except Exception as exc:
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during TracerProvider shutdown: {exc}")

        # Then shutdown custom PostHog client
        if self.custom_posthog_client:
            try:
                self.custom_posthog_client.shutdown()
            except Exception as exc:
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during custom PostHog shutdown: {exc}")

        # Then shutdown Pipelex PostHog client
        if self.pipelex_posthog_client:
            try:
                self.pipelex_posthog_client.shutdown()
            except Exception as exc:
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during Pipelex PostHog shutdown: {exc}")

        # Clear singleton instance
        TelemetryManagerAbstract.clear_instance()

    @override
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        # We copy the incoming properties to avoid modifying the original dictionary
        # and to convert the keys to str
        # and to remove the properties that are in the redact list
        tracked_properties: dict[str, Any]
        if properties:
            tracked_properties = {key: value for key, value in properties.items() if key not in self.telemetry_config.redact_properties}
        else:
            tracked_properties = {}

        # Track to custom PostHog based on user's posthog.mode
        match self.telemetry_config.custom_posthog.mode:
            case PostHogMode.ANONYMOUS:
                self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
            case PostHogMode.IDENTIFIED:
                if not self.telemetry_config.custom_posthog.user_id:
                    log.error(f"Could not track event '{event_name}' as identified because user_id is not set, tracking as anonymous")
                    self._track_anonymous_event(event_name=event_name, properties=tracked_properties)
                else:
                    self._track_identified_event(
                        event_name=event_name,
                        properties=tracked_properties,
                        user_id=self.telemetry_config.custom_posthog.user_id,
                    )
            case PostHogMode.OFF:
                log.verbose(f"Custom telemetry is off, skipping event '{event_name}' for custom client")

        # Always track to Pipelex PostHog if enabled (independent of posthog.mode)
        if self._pipelex_telemetry_enabled:
            self._track_to_pipelex(event_name=event_name, properties=tracked_properties)

    def _track_anonymous_event(self, event_name: str, properties: dict[str, Any]):
        if not self.custom_posthog_client:
            log.error("Could not track event to custom telemetry because custom_posthog_client is not set")
            return
        properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
        self.custom_posthog_client.capture(event_name, properties=properties)
        log.verbose(f"Tracked anonymous event '{event_name}' with properties: {properties}")

    def _track_identified_event(self, event_name: str, properties: dict[str, Any], user_id: str):
        if not self.custom_posthog_client:
            log.error("Could not track event to custom telemetry because custom_posthog_client is not set")
            return
        self.custom_posthog_client.capture(event_name, distinct_id=user_id, properties=properties)
        log.verbose(f"Tracked identified event '{event_name}' with properties: {properties}")

    def _track_to_pipelex(self, event_name: str, properties: dict[str, Any]):
        """Track event to Pipelex's PostHog (always identified)."""
        if not self.pipelex_posthog_client or not self._pipelex_distinct_id:
            log.error("Could not track event to Pipelex telemetry because pipelex_posthog_client or _pipelex_distinct_id is not set")
            return
        self.pipelex_posthog_client.capture(event_name, distinct_id=self._pipelex_distinct_id, properties=properties)
        log.verbose(f"Tracked event '{event_name}' to Pipelex telemetry")

    @override
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """Context manager that uses PostHog's new_context when telemetry is enabled."""
        with new_context():
            yield

    @override
    def is_custom_portkey_logging_enabled(self, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if not is_debug and self.telemetry_config.custom_portkey.force_debug_enabled:
            log.verbose("Force-enabling Portkey logging (debug mode) because custom_portkey.force_debug_enabled is set in telemetry configuration")
            is_debug = True
        if is_debug and is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.warning(
                f"Disabling Custom Portkey logging (debug mode) "
                f"because '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}' is set and that setting takes precedence"
            )
            is_debug = False
        return is_debug

    @override
    def is_custom_portkey_tracing_enabled(self) -> bool:
        if self.telemetry_config.custom_portkey.force_tracing_enabled and not is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.info("Force-enabling Portkey tracing because custom_portkey.force_tracing_enabled is set in telemetry configuration")
            return True
        else:
            return False

    @override
    def is_pipelex_gateway_portkey_logging_enabled(self, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if (
            not is_debug
            and self.telemetry_config.pipelex_gateway
            and self.telemetry_config.pipelex_gateway.portkey
            and self.telemetry_config.pipelex_gateway.portkey.force_debug_enabled
        ):
            log.dev(
                "Force-enabling Portkey logging (debug mode) because pipelex_gateway.portkey.force_debug_enabled is set in telemetry configuration"
            )
            is_debug = True
        if is_debug and is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY):
            log.warning(
                f"Disabling Pipelex Gateway Portkey logging (debug mode) "
                f"because '{OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY}' is set and that setting takes precedence"
            )
            is_debug = False
        return is_debug

    @override
    def is_pipelex_gateway_portkey_tracing_enabled(self) -> bool:
        if (
            self.telemetry_config.pipelex_gateway
            and self.telemetry_config.pipelex_gateway.portkey
            and self.telemetry_config.pipelex_gateway.portkey.force_tracing_enabled
            and not is_env_var_truthy(OTelConstants.DO_NOT_TRACK_ENV_VAR_KEY)
        ):
            log.verbose(
                "Force-enabling Pipelex Gateway Portkey tracing "
                "because pipelex_gateway.portkey.force_tracing_enabled is set in telemetry configuration"
            )
            return True
        else:
            return False

    @override
    def get_otel_tracer(self) -> OTelTracer | None:
        return self._otel_tracer

    @property
    @override
    def capture_content_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.content

    @property
    @override
    def capture_pipe_codes_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.pipe_codes

    @property
    @override
    def capture_output_class_name_enabled(self) -> bool:
        return self.telemetry_config.custom_posthog.tracing.capture.output_class_names

    @property
    @override
    def capture_content_max_length(self) -> int | None:
        return self.telemetry_config.custom_posthog.tracing.capture.content_max_length

    @property
    @override
    def is_langfuse_enabled(self) -> bool:
        return self.telemetry_config.langfuse.enabled

    @property
    @override
    def is_pipelex_telemetry_enabled(self) -> bool:
        return self._pipelex_telemetry_enabled

    @override
    def handle_trace_start(self, trace_name: str, trace_name_redacted: str, trace_id: int) -> None:
        """Hook to do something when a trace starts.

        Emits a trace start event to establish the trace name in PostHog.
        We send a minimal $ai_span event with the trace_name as the span name.
        This event is sent directly (not via OTel spans) to ensure it arrives
        before any batched pipe spans, establishing the correct trace name.

        Args:
            trace_name: Full trace name with pipe code (for custom telemetry).
            trace_name_redacted: Redacted trace name without pipe code (for Pipelex telemetry).
            trace_id: The trace ID.
        """
        log.verbose(
            f"[Telemetry] Emitting trace start event:\n"
            f"  trace_name='{trace_name}'\n"
            f"  trace_name_redacted='{trace_name_redacted}'\n"
            f"  trace_id={trace_id:032x}"
        )

        # Send to custom PostHog if configured (uses full trace name based on user's capture settings)
        if self.custom_posthog_client and self.telemetry_config.custom_posthog.tracing.enabled:
            # Use full or redacted trace name based on user's capture_pipe_codes setting
            custom_trace_name = trace_name if self.telemetry_config.custom_posthog.tracing.capture.pipe_codes else trace_name_redacted
            custom_properties: dict[str, Any] = {
                PostHogAttr.TRACE_ID: f"{trace_id:032x}",
                PostHogAttr.SPAN_NAME: custom_trace_name,
                PostHogAttr.TRACE_NAME: custom_trace_name,
            }
            if self.telemetry_config.custom_posthog.user_id:
                self.custom_posthog_client.capture(
                    distinct_id=self.telemetry_config.custom_posthog.user_id,
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                )
            else:
                custom_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
                self.custom_posthog_client.capture(
                    event=PostHogEvent.SPAN,
                    properties=custom_properties,
                )

        # Send to Pipelex PostHog if gateway telemetry is enabled (always uses redacted trace name)
        if self.pipelex_posthog_client:
            pipelex_properties: dict[str, Any] = {
                PostHogAttr.TRACE_ID: f"{trace_id:032x}",
                PostHogAttr.SPAN_NAME: trace_name_redacted,
                PostHogAttr.TRACE_NAME: trace_name_redacted,
            }
            if self._pipelex_distinct_id:
                self.pipelex_posthog_client.capture(
                    distinct_id=self._pipelex_distinct_id,
                    event=PostHogEvent.SPAN,
                    properties=pipelex_properties,
                )
            else:
                pipelex_properties[PostHogAttr.PROCESS_PERSON_PROFILE] = False
                self.pipelex_posthog_client.capture(
                    event=PostHogEvent.SPAN,
                    properties=pipelex_properties,
                )
