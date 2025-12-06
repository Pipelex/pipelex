from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry.trace import Tracer
from typing_extensions import override

from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.telemetry_config import TelemetryConfig, TelemetryMode


class TelemetryManagerAbstract(ABC):
    telemetry_mode_just_set: TelemetryMode | None = None

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
    def get_tracer(self) -> Tracer | None:
        """Get the OpenTelemetry tracer for GenAI spans, if configured."""

    @abstractmethod
    def get_telemetry_config(self) -> TelemetryConfig | None:
        """Get the telemetry configuration, if available."""


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
    def get_tracer(self) -> Tracer | None:
        return None

    @override
    def get_telemetry_config(self) -> TelemetryConfig | None:
        return None
