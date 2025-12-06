from contextlib import contextmanager
from typing import Any, Callable, Generator

import posthog
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from posthog import Posthog, new_context, tag  # type: ignore[attr-defined]
from posthog.args import ExceptionArg, OptionalCaptureArgs
from typing_extensions import Unpack, override

from pipelex.plugins.portkey.portkey_constants import PortkeyEnvVar
from pipelex.system.environment import is_env_var_truthy
from pipelex.system.exceptions import PipelexError
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty, Setting
from pipelex.system.telemetry.otel_utils import set_global_tracer
from pipelex.system.telemetry.posthog_span_exporter import PostHogSpanExporter
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

        # Create OTel tracer for AI tracing if enabled
        self._tracer: Tracer | None
        self._tracer_provider: TracerProvider | None
        if telemetry_config.ai_tracing_enabled:
            self._tracer, self._tracer_provider = self.make_ai_tracer(
                posthog_client=self.posthog_client,
                user_id=telemetry_config.user_id,
                otlp_endpoint=telemetry_config.otlp_endpoint,
                otlp_headers=telemetry_config.otlp_headers,
            )
            # Set the global tracer for modules that can't import from hub (avoids circular imports)
            set_global_tracer(self._tracer)
            log.dev("AI tracing enabled: OpenTelemetry tracer created")
        else:
            self._tracer = None
            self._tracer_provider = None
            set_global_tracer(None)
            log.dev("AI tracing disabled: No OpenTelemetry tracer created")

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
            """Capture exception with message sanitization for PipelexError subclasses."""
            if exception and isinstance(exception, PipelexError):
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
                # For non-PipelexError, capture as-is (or auto-detect current exception)
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
        # First, shutdown the TracerProvider to flush all pending spans
        # This MUST happen before PostHog shutdown, otherwise spans won't be exported
        if self._tracer_provider:
            try:
                log.dev("Shutting down OTel TracerProvider (flushing pending spans)...")
                self._tracer_provider.shutdown()
                log.dev("OTel TracerProvider shutdown complete")
            except Exception as exc:
                # Suppress any shutdown errors to avoid cascading failures
                log.debug(f"Error during TracerProvider shutdown: {exc}")

        # Then shutdown PostHog client
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
                    self._track_identified_event(
                        event_name=event_name,
                        properties=tracked_properties,
                        user_id=self.telemetry_config.user_id,
                    )
            case TelemetryMode.OFF:
                log.verbose(f"Telemetry is off, skipping event '{event_name}'")

    def _track_anonymous_event(self, event_name: str, properties: dict[str, Any]):
        if not self.posthog_client:
            return
        if self.telemetry_config.dry_mode_enabled:
            if properties:
                log.debug(
                    properties,
                    title=f"Tracking anonymous event '{event_name}'. Properties",
                )
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
                log.debug(
                    properties,
                    title=f"Tracking identified event '{event_name}'. Properties",
                )
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

    @override
    def is_portkey_logging_enabled(self, is_debug_configured: bool) -> bool:
        is_debug: bool = is_debug_configured
        if not is_debug and is_env_var_truthy(PortkeyEnvVar.FORCE_PORTKEY_DEBUG):
            log.info(f"Force-enabling Portkey logging (debug mode) because '{PortkeyEnvVar.FORCE_PORTKEY_DEBUG}' is set")
            is_debug = True
        if is_debug and is_env_var_truthy(DO_NOT_TRACK_ENV_VAR_KEY):
            log.warning(f"Disabling Portkey logging (debug mode) because '{DO_NOT_TRACK_ENV_VAR_KEY}' is set and that setting takes precedence")
            is_debug = False
        return is_debug

    @override
    def is_portkey_tracing_enabled(self) -> bool:
        if is_env_var_truthy(PortkeyEnvVar.FORCE_PORTKEY_TRACING):
            log.info(f"Force-enabling Portkey tracing because '{PortkeyEnvVar.FORCE_PORTKEY_TRACING}' is set")
            return True
        else:
            return False

    @override
    def get_tracer(self) -> Tracer | None:
        return self._tracer

    @override
    def get_telemetry_config(self) -> TelemetryConfig | None:
        return self.telemetry_config

    def make_ai_tracer(
        self,
        posthog_client: Posthog | None,
        user_id: str,
        otlp_endpoint: str | None = None,
        otlp_headers: dict[str, str] | None = None,
    ) -> tuple[Tracer, TracerProvider]:
        """Create an isolated OpenTelemetry Tracer for GenAI instrumentation.

        This creates a dedicated TracerProvider that does NOT register itself as the
        global tracer to avoid polluting other traces in the host application.

        It can configure two types of exporters:
        1. PostHog Exporter: Converts spans to PostHog $ai_generation events
        2. OTLP Exporter: Sends standard OTLP traces to a collector

        Args:
            posthog_client: Optional PostHog client for sending events
            user_id: User ID for event attribution
            otlp_endpoint: Optional OTLP endpoint URL
            otlp_headers: Optional headers for OTLP export

        Returns:
            A tuple of (Tracer, TracerProvider). The caller should call
            provider.shutdown() during teardown to flush pending spans.
        """
        # 1. Define Resource (Identity)
        resource = Resource.create(
            {
                "service.name": "pipelex-ai",
                "service.version": get_package_version(),
                "service.namespace": "ai.orchestration",
            }
        )

        # 2. Create Provider
        provider = TracerProvider(resource=resource)

        # 3. Add PostHog Exporter if client provided
        if posthog_client:
            posthog_exporter = PostHogSpanExporter(posthog_client, user_id=user_id)
            provider.add_span_processor(BatchSpanProcessor(posthog_exporter))

        # 4. Add Generic OTLP Exporter if endpoint provided
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=otlp_headers or {},
            )
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # 5. Get the Tracer and return both tracer and provider
        tracer = provider.get_tracer("pipelex", get_package_version())
        return tracer, provider
