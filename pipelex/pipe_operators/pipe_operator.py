from abc import abstractmethod
from typing import TYPE_CHECKING, Generic, Literal, TypeVar, final

from typing_extensions import override

from pipelex.cogt.exceptions import ModelNotFoundError, ModelWaterfallError
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.stuffs.list_content import ListContent
    from pipelex.core.stuffs.stuff_content import StuffContent

PipeOperatorOutputType = TypeVar("PipeOperatorOutputType", bound=PipeOutput)


class PipeOperator(PipeAbstract, Generic[PipeOperatorOutputType]):
    pipe_category: Literal["PipeOperator"] = "PipeOperator"

    @property
    def class_name(self) -> str:
        return self.__class__.__name__

    @final
    @override
    async def _live_run_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        try:
            pipe_output = await self._live_run_operator_pipe(
                job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
            )

            main_stuff = pipe_output.main_stuff
            output_concept_code = self.output.concept.code
            output_concept_with_multiplicity = f"[bold green]{output_concept_code}[/bold green]"
            if main_stuff.is_list:
                list_content: ListContent[StuffContent] = main_stuff.as_list_content()  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
                nb_items = len(list_content.items)
                if nb_items == 1:
                    output_concept_with_multiplicity += " [1 item]"
                else:
                    output_concept_with_multiplicity += f" [{nb_items} items]"
            title = f"Output of pipe [red]{self.code}[/red] [yellow]→[/yellow] {output_concept_with_multiplicity}"
            main_stuff.pretty_print_stuff(title=title)

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
        return pipe_output

    @final
    @override
    async def _dry_run_pipe(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ) -> PipeOutput:
        return await self._dry_run_operator_pipe(
            job_metadata=job_metadata, working_memory=working_memory, pipe_run_params=pipe_run_params, output_name=output_name
        )

    @abstractmethod
    async def _live_run_operator_pipe(
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
