from abc import ABC, abstractmethod
from typing import Any


class TelemetryManagerAbstract(ABC):
    @abstractmethod
    def setup(self):
        pass

    @abstractmethod
    def teardown(self):
        pass

    @abstractmethod
    def track_event(self, event_name: str, event_data: dict[str, Any] | None = None):
        pass
