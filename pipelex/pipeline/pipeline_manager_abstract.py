from abc import ABC, abstractmethod

from pipelex.pipeline.pipeline import Pipeline


class PipelineManagerAbstract(ABC):
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def teardown(self) -> None:
        pass

    @abstractmethod
    def get_optional_pipeline(self, pipeline_run_id: str) -> Pipeline | None:
        pass

    @abstractmethod
    def get_pipeline(self, pipeline_run_id: str) -> Pipeline:
        pass

    @abstractmethod
    def add_new_pipeline(self, pipe_code: str | None, pipeline_run_id: str | None = None) -> Pipeline:
        pass

    @abstractmethod
    def remove_pipeline(self, pipeline_run_id: str) -> None:
        """Forget a run's entry so the same ``pipeline_run_id`` can be resubmitted later.

        Tolerant: a no-op when the entry is absent (setup may have failed before
        the registration committed).
        """
