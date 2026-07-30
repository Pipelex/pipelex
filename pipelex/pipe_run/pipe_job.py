from typing import Any

from pydantic import BaseModel

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.exceptions import PipeJobError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata


class PipeJob(BaseModel):
    pipe: PipeAbstract
    working_memory: WorkingMemory | None = None
    working_memory_raw: dict[str, Any] | None = None
    pipe_run_params: PipeRunParams
    job_metadata: JobMetadata
    output_name: str | None = None
    library_crate: LibraryCrate | None = None

    @property
    def pipe_type(self) -> str:
        return self.pipe.__class__.__name__

    def get_working_memory(self) -> WorkingMemory:
        if self.working_memory is not None:
            return self.working_memory
        if self.working_memory_raw is not None:
            msg = "WorkingMemory is in raw form and has not been hydrated yet"
            raise PipeJobError(msg)
        return WorkingMemory()
