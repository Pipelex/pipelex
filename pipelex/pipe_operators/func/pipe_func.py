import asyncio
from typing import Literal, cast, get_type_hints

from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.input_requirements import InputRequirements, TypedNamedInputRequirement
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import DryRunError
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator[PipeFuncOutput]):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str

    @override
    def required_variables(self) -> set[str]:
        return set()

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        return self.inputs

    @override
    def validate_output(self):
        pass

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        log.debug(f"Applying function '{self.function_name}'")

        function = func_registry.get_required_function(self.function_name)

        if asyncio.iscoroutinefunction(function):
            func_output_object = await function(working_memory=working_memory)
        else:
            func_output_object = await asyncio.to_thread(function, working_memory=working_memory)

        the_content: StuffContent
        if isinstance(func_output_object, StuffContent):
            the_content = func_output_object
        elif isinstance(func_output_object, list):
            func_result_list = cast("list[StuffContent]", func_output_object)
            the_content = ListContent(items=func_result_list)
        elif isinstance(func_output_object, str):
            the_content = TextContent(text=func_output_object)
        else:
            msg = f"Function '{self.function_name}' must return a StuffContent or a list, got {type(func_output_object)}"
            raise TypeError(msg)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        log.debug(f"Dry run for PipeFunc '{self.function_name}'")

        function = func_registry.get_required_function(self.function_name)

        # Check that all needed inputs are present in working memory
        needed_inputs = self.needed_inputs()
        for input_name, _ in needed_inputs.items:
            if input_name not in working_memory.root:
                msg = f"Required input '{input_name}' not found in working memory for function '{self.function_name}' in pipe '{self.code}'"
                raise DryRunError(msg)

        try:
            return_type = get_type_hints(function).get("return")

            if return_type is None:
                msg = f"Function '{self.function_name}' has no return type annotation"
                raise DryRunError(msg)
            if not issubclass(return_type, StuffContent):
                msg = f"Function '{self.function_name}' return type {return_type} is not a subclass of StuffContent"
                raise DryRunError(msg)

            requirement = TypedNamedInputRequirement(
                variable_name="mock_output",
                concept=ConceptFactory.make(
                    concept_code=self.output.code,
                    domain="generic",
                    description="Lorem Ipsum",
                    structure_class_name=self.output.structure_class_name,
                ),
                structure_class=return_type,
                multiplicity=False,
            )
            mock_content = WorkingMemoryFactory.create_mock_content(requirement)

        except Exception as exc:
            msg = f"Failed to get type hints for function '{self.function_name}' in pipe '{self.code}': {exc}"
            raise DryRunError(msg) from exc

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output,
            content=mock_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
