from typing import Optional

from pydantic import BaseModel, Field

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory = Field(default_factory=WorkingMemory)
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: Optional[str] = None
