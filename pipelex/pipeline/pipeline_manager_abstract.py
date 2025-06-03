from abc import ABC, abstractmethod
from typing import Optional

from pipelex.pipeline.pipeline import Pipeline


class PipelineManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def get_optional_mission(self, mission_id: str) -> Optional[Pipeline]:
        pass

    @abstractmethod
    def get_mission(self, mission_id: str) -> Pipeline:
        pass

    @abstractmethod
    def add_new_mission(self) -> Pipeline:
        pass
