from abc import abstractmethod
from typing import Literal

from typing_extensions import override

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_run.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeController(PipeAbstract):
    pipe_category: Literal["PipeController"] = "PipeController"

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    @override
    async def run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        print_intermediate_outputs: bool | None = False,
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
                label = (
                    f"{indent}{'[yellow]↳[/yellow]' if indent_level > 0 else ''} Running [blue]{self.class_name}[/blue] → [green]{self.code}[/green]"
                )
                log.info(f"{label} → [red]{self.output.code}[/red]")
                pipe_output = await self._run_controller_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
            case PipeRunMode.DRY:
                name = f"Dry running [blue]{self.class_name}[/blue]"
                indent_level = len(pipe_run_params.pipe_stack) - 1
                indent = "   " * indent_level
                label = f"{indent}{'[yellow]↳[/yellow]' if indent_level > 0 else ''} {name}: [green]{self.code}[/green]"
                log.info(f"{label} → [red]{self.output.code}[/red]")
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
