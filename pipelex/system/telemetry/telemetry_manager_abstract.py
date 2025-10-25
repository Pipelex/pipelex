from abc import ABC, abstractmethod
from typing import Any

from typing_extensions import override

from pipelex.system.telemetry.events import EventName, EventProperty


class TelemetryManagerAbstract(ABC):
    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass

    @abstractmethod
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        pass


class TelemetryManagerNoOp(TelemetryManagerAbstract):
    @override
    def setup(self):
        pass

    @override
    def teardown(self):
        pass

    @override
    def track_event(self, event_name: EventName, properties: dict[EventProperty, Any] | None = None):
        pass
