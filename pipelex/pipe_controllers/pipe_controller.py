from abc import abstractmethod
from typing import Literal, final

from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeController(PipeAbstract):
    pipe_category: Literal["PipeController"] = "PipeController"

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    def pipe_dependencies(self) -> set[str]:
        """Return the pipes that are dependencies of the pipe.
        - PipeBatch: The pipe that is being batched
        - PipeCondition: The pipes in the outcome_map
        - PipeSequence: The pipes in the steps
        """

    @final
    @override
    async def _live_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        return await self._live_run_controller_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

    @final
    @override
    async def _dry_run_pipe(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ) -> PipeOutput:
        return await self._dry_run_controller_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

    @abstractmethod
    async def _live_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pass

    @abstractmethod
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pass
