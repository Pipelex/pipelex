from abc import abstractmethod
from typing import Generic, Literal, TypeVar

from typing_extensions import override

from pipelex import log, pretty_print, pretty_print_md
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.text_content import TextContent
from pipelex.hub import get_activity_manager
from pipelex.pipe_run.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipeline.activity.activity_models import ActivityReport
from pipelex.pipeline.job_metadata import JobMetadata

PipeOperatorOutputType = TypeVar("PipeOperatorOutputType", bound=PipeOutput)


class PipeOperator(PipeAbstract, Generic[PipeOperatorOutputType]):
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

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
                if self.class_name not in ["PipeCompose", "PipeLLMPrompt"]:
                    name = f"Running [cyan]{self.class_name}[/cyan]"
                    indent_level = len(pipe_run_params.pipe_stack) - 1
                    indent = "   " * indent_level
                    label = f"{indent}{'[yellow]↳[/yellow]' if indent_level > 0 else ''} {name} → [green]{self.code}[/green]"
                    log.info(f"{label} → [red]{self.output.code}[/red]")
                pipe_output = await self._run_operator_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
                if isinstance(pipe_output.main_stuff.content, TextContent):
                    pretty_print_md(pipe_output.main_stuff_as_str, title=f"PipeOutput of pipe {self.code}")
                else:
                    pretty_print(pipe_output.main_stuff, title=f"PipeOutput of pipe {self.code}")
            case PipeRunMode.DRY:
                name = f"Dry run [cyan]{self.class_name}[/cyan]"
                indent_level = len(pipe_run_params.pipe_stack) - 1
                indent = "   " * indent_level
                label = f"{indent}{'[yellow]↳[/yellow]' if indent_level > 0 else ''} {name}: [green]{self.code}[/green]"
                log.info(f"{label} → [red]{self.output.code}[/red]")
                pipe_output = await self._dry_run_operator_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=pipe_run_params,
                    output_name=output_name,
                )
        get_activity_manager().dispatch_activity(
            activity_report=ActivityReport(
                job_metadata=job_metadata,
                content=pipe_output.main_stuff,
            ),
        )

        pipe_run_params.pop_pipe_from_stack(pipe_code=self.code)

        return pipe_output

    @abstractmethod
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOperatorOutputType:
        pass

    @abstractmethod
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOperatorOutputType:
        pass
