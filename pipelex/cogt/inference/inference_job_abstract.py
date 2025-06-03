from abc import ABC, abstractmethod

from pydantic import BaseModel

from pipelex.pipeline.job_metadata import JobMetadata


class InferenceJobAbstract(ABC, BaseModel):
    job_metadata: JobMetadata

    @abstractmethod
    def validate_before_execution(self):
        pass
