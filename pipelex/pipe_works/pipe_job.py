from typing import Optional

from pydantic import BaseModel, Field

from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.pipeline.job_metadata import JobMetadata


class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: Optional[str] = None
