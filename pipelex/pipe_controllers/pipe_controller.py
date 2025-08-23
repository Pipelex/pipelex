from abc import abstractmethod
from typing import Optional

from typing_extensions import override

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeController(PipeAbstract):
    @override
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_to_stack(pipe_code=self.code)
        self.monitor_pipe_stack(pipe_run_params=pipe_run_params)

        updated_metadata = JobMetadata(
            pipe_job_ids=[self.code],
        )
        job_metadata.update(updated_metadata=updated_metadata)

        match pipe_run_params.run_mode:
            case PipeRunMode.LIVE:
                indent_level = len(pipe_run_params.pipe_stack) - 1
                indent = "   " * indent_level
                label = f"{indent}{self.class_name}: {self.code}".ljust(80)
                output = self.output.code
                log.info(f"{label} → {output}")
                pipe_output = await self._run_controller_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
            case PipeRunMode.DRY:
                name = f"Dry {self.class_name}"
                indent_level = len(pipe_run_params.pipe_stack) - 1
                indent = "   " * indent_level
                label = f"{indent}{name}: {self.code}".ljust(80)
                output = self.output.code
                log.info(f"{label} → {output}")
                pipe_output = await self._dry_run_controller_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)
        return pipe_output

    @abstractmethod
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pass

    @abstractmethod
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pass
