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
    def is_capture_output_class_name_enabled(cls) -> bool:
        """Check if output class name capture is enabled for telemetry.

        When this returns False, output class names should be redacted from span names
        and attributes.

        Returns:
            True if output class name capture is enabled, False otherwise (including when
            no telemetry manager is configured).
        """
        instance = cls.get_instance()
        if instance is None:
            return False
        return instance.capture_output_class_name_enabled

    @classmethod
    def get_capture_content_max_length(cls) -> int | None:
        """Get the maximum length for captured content.

        Returns:
            The maximum length for captured content, or None if unlimited
            (including when no telemetry manager is configured).
        """
        instance = cls.get_instance()
        if instance is None:
            return None
        return instance.capture_content_max_length

    @classmethod
    def get_langfuse_enabled(cls) -> bool:
        """Check if Langfuse OTLP exporter is enabled for telemetry.

        Returns:
            True if Langfuse OTLP exporter is enabled, False otherwise (including when
            no telemetry manager is configured).
        """
        instance = cls.get_instance()
        if instance is None:
            return False
        return instance.is_langfuse_enabled

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

    @property
    @abstractmethod
    def capture_output_class_name_enabled(self) -> bool:
        """Whether output class names should appear in span names and attributes."""

    @property
    @abstractmethod
    def capture_content_max_length(self) -> int | None:
        """Maximum length for captured content, or None if unlimited."""

    @property
    @abstractmethod
    def is_langfuse_enabled(self) -> bool:
        """Whether Langfuse OTLP exporter is enabled."""

    @property
    @abstractmethod
    def is_pipelex_telemetry_enabled(self) -> bool:
        """Whether Pipelex internal telemetry is enabled (for gateway usage)."""

    @abstractmethod
    def handle_trace_start(self, trace_name: str, trace_id: int) -> None:
        """Hook to do something when a trace starts and just got its trace_name and trace_id."""


class TelemetryManagerNoOp(TelemetryManagerAbstract):
    @override
    def setup(self, integration_mode: IntegrationMode):
        pass

    @override
    def teardown(self):
        # Clear singleton instance to allow telemetry to be re-enabled in the same process
        TelemetryManagerAbstract.clear_instance()

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

    @property
    @override
    def capture_output_class_name_enabled(self) -> bool:
        return False

    @property
    @override
    def capture_content_max_length(self) -> int | None:
        return None

    @property
    @override
    def is_langfuse_enabled(self) -> bool:
        return False

    @property
    @override
    def is_pipelex_telemetry_enabled(self) -> bool:
        return False

    @override
    def handle_trace_start(self, trace_name: str, trace_id: int) -> None:
        pass
