from abc import abstractmethod
from typing import Generic, Literal, TypeVar

from typing_extensions import override

from pipelex import log, pretty_print_md
from pipelex.cogt.exceptions import ModelNotFoundError, ModelWaterfallError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params import PipeRunParams
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

        try:
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
                        print()
                        pretty_print_md(pipe_output.main_stuff_as_str, title=f"PipeOutput of pipe {self.code}")
                        print()
                    else:
                        print()
                        pipe_output.main_stuff.pretty_print_stuff(title=f"PipeOutput of pipe {self.code}: {self.output.code}")
                        print()
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
        except ModelWaterfallError as model_waterfall_error:
            raise PipeOperatorModelAvailabilityError(
                message=model_waterfall_error.message,
                run_mode=pipe_run_params.run_mode,
                pipe_type=self.class_name,
                pipe_code=self.code,
                pipe_stack=pipe_run_params.pipe_stack,
                model_handle=model_waterfall_error.model_handle,
                fallback_list=model_waterfall_error.fallback_list,
            ) from model_waterfall_error
        except ModelNotFoundError as model_not_found_error:
            raise PipeOperatorModelAvailabilityError(
                message=model_not_found_error.message,
                run_mode=pipe_run_params.run_mode,
                pipe_type=self.class_name,
                pipe_code=self.code,
                pipe_stack=pipe_run_params.pipe_stack,
                model_handle=model_not_found_error.model_handle,
                fallback_list=None,
            ) from model_not_found_error
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
