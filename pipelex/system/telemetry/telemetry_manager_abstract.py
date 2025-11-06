from abc import ABC, abstractmethod
from typing import Any

from typing_extensions import override

from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
from pipelex.system.telemetry.telemetry_config import TelemetryMode


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
