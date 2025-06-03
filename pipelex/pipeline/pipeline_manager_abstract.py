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
    def get_optional_pipeline(self, pipeline_run_id: str) -> Optional[Pipeline]:
        pass

    @abstractmethod
    def get_pipeline(self, pipeline_run_id: str) -> Pipeline:
        pass

    @abstractmethod
    def add_new_pipeline(self) -> Pipeline:
        pass
