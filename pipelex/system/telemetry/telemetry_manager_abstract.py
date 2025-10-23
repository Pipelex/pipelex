from abc import ABC, abstractmethod
from typing import Any

from pipelex.system.telemetry.telemetry_config import TelemetryConfig


class TelemetryManagerAbstract(ABC):
    @abstractmethod
    def get_telemetry_config(self) -> TelemetryConfig:
        pass

    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass

    @abstractmethod
    def track_event(self, event_name: str, event_data: dict[str, Any] | None = None):
        pass
