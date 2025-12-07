from abc import abstractmethod
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry.trace import Tracer as OTelTracer
from typing_extensions import override

from pipelex.system.registries.singleton import ABCSingletonMeta, MetaSingleton
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.telemetry_config import TelemetryMode


class TelemetryManagerAbstract(metaclass=ABCSingletonMeta):
    telemetry_mode_just_set: TelemetryMode | None = None

    @classmethod
    def clear_instance(cls) -> None:
        """Clear the singleton instance from MetaSingleton registry."""
        MetaSingleton.clear_subclass_instances(TelemetryManagerAbstract)

    @classmethod
    def get_instance(cls) -> "TelemetryManagerAbstract | None":
        """Get the singleton instance from MetaSingleton registry.

        This provides a way to access the telemetry manager without importing from hub,
        avoiding circular dependency issues.
        """
        return MetaSingleton.get_subclass_instance(TelemetryManagerAbstract)  # type: ignore[type-abstract]

    @classmethod
    def get_instance_tracer(cls) -> OTelTracer | None:
        """Get the tracer from the singleton instance.

        This provides a way to access the tracer without importing from hub,
        avoiding circular dependency issues.
        """
        instance = cls.get_instance()
        if instance is None:
            return None
        return instance.get_otel_tracer()

    @classmethod
    def is_capture_content_enabled(cls) -> bool:
        """Check if content capture is enabled for telemetry.

        When this returns False, prompt/completion content should not be
        captured in span attributes.

        Returns:
            True if content capture is enabled, False otherwise (including when
            no telemetry manager is configured).
        """
        instance = cls.get_instance()
        if instance is None:
            return False
        return instance.capture_content_enabled

    @classmethod
    def is_capture_pipe_codes_enabled(cls) -> bool:
        """Check if pipe code capture is enabled for telemetry.

        When this returns False, pipe codes should be redacted from span names
        and attributes, and excluded from run IDs.

        Returns:
            True if pipe code capture is enabled, False otherwise (including when
            no telemetry manager is configured).
        """
        instance = cls.get_instance()
        if instance is None:
            return False
        return instance.capture_pipe_codes_enabled

    @classmethod
    def telemetry_was_just_enabled(cls) -> TelemetryMode | None:
        if cls.telemetry_mode_just_set is None:
            return None
        else:
            return cls.telemetry_mode_just_set if cls.telemetry_mode_just_set.is_enabled else None

    @abstractmethod
    def setup(self, integration_mode: IntegrationMode):
        pass

    @abstractmethod
    def teardown(self):
        pass

    @abstractmethod
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        pass

    @abstractmethod
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """Safe context manager for telemetry that works whether telemetry is enabled or not."""

    @abstractmethod
    def is_portkey_logging_enabled(self, is_debug_configured: bool) -> bool:
        pass

    @abstractmethod
    def is_portkey_tracing_enabled(self) -> bool:
        pass

    @abstractmethod
    def get_otel_tracer(self) -> OTelTracer | None:
        """Get the OpenTelemetry tracer for GenAI spans, if configured."""

    @property
    @abstractmethod
    def capture_content_enabled(self) -> bool:
        """Whether prompt/completion content should be captured in span attributes."""

    @property
    @abstractmethod
    def capture_pipe_codes_enabled(self) -> bool:
        """Whether pipe codes should appear in span names and attributes."""

    @abstractmethod
    def emit_trace_start(self, pipeline_run_id: str, trace_id: int) -> None:
        """Emit a trace start event to establish the trace name in PostHog.

        This should be called at the very beginning of pipeline execution,
        before any pipe spans are created. PostHog uses the first $ai_span_name
        it receives to name the trace, so this event ensures the trace is named
        after the pipeline_run_id rather than the first child span.

        Args:
            pipeline_run_id: The pipeline run ID to use as the trace name.
            trace_id: The 128-bit trace ID for correlation.
        """


class TelemetryManagerNoOp(TelemetryManagerAbstract):
    @override
    def setup(self, integration_mode: IntegrationMode):
        pass

    @override
    def teardown(self):
        pass

    @override
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        pass

    @override
    @contextmanager
    def telemetry_context(self) -> Generator[None, None, None]:
        """No-op context manager that doesn't use PostHog."""
        yield

    @override
    def is_portkey_logging_enabled(self, is_debug_configured: bool) -> bool:
        return False

    @override
    def is_portkey_tracing_enabled(self) -> bool:
        return False

    @override
    def get_otel_tracer(self) -> OTelTracer | None:
        return None

    @property
    @override
    def capture_content_enabled(self) -> bool:
        return False

    @property
    @override
    def capture_pipe_codes_enabled(self) -> bool:
        return False

    @override
    def emit_trace_start(self, pipeline_run_id: str, trace_id: int) -> None:
        pass
