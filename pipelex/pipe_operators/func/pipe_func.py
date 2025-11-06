import asyncio
from typing import Literal, cast, get_type_hints

from pydantic import field_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.pipes.input_requirements import InputRequirements, TypedNamedInputRequirement
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.exceptions import DryRunMissingInputsError
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.system.registries.func_registry import func_registry


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator[PipeFuncOutput]):
    type: Literal["PipeFunc"] = "PipeFunc"
    function_name: str

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, function_name: str) -> str:
        function = func_registry.get_function(function_name)
        if not function:
            msg = f"Function '{function_name}' not found in registry"
            raise PipeDefinitionError(msg)

        return_type = get_type_hints(function).get("return")

        if return_type is None:
            msg = f"Function '{function_name}' has no return type annotation"
            raise PipeDefinitionError(msg)
        if not issubclass(return_type, StuffContent):
            msg = f"Function '{function_name}' return type {return_type} is not a subclass of StuffContent"
            raise PipeDefinitionError(msg)
        return function_name

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
        log.verbose(f"Applying function '{self.function_name}'")

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
        log.verbose(f"Dry run for PipeFunc '{self.function_name}'")

        function = func_registry.get_required_function(self.function_name)

        # Check that all needed inputs are present in working memory
        needed_inputs = self.needed_inputs()

        missing_input_names: list[str] = []
        for named_input_requirement in needed_inputs.named_input_requirements:
            if not working_memory.get_optional_stuff(named_input_requirement.variable_name):
                missing_input_names.append(named_input_requirement.variable_name)
        if missing_input_names:
            msg = f"Dry run failed for PipeFunc (function '{self.function_name}'): missing required inputs: {missing_input_names}"
            log.error(f"Dry run failed: missing required inputs: {missing_input_names}")
            raise DryRunMissingInputsError(
                message=msg,
                pipe_type=self.__class__.__name__,
                pipe_code=self.code,
                missing_inputs=missing_input_names,
            )

        return_type = get_type_hints(function).get("return")

        if return_type is None:
            msg = f"Function '{self.function_name}' has no return type annotation"
            raise PipeDefinitionError(msg)
        if not issubclass(return_type, StuffContent):
            msg = f"Function '{self.function_name}' return type {return_type} is not a subclass of StuffContent"
            raise PipeDefinitionError(msg)

        # TODO: Support PipeFunc returning with multiplicity. Create an equivalent of TypedNamedInputRequirement for outputs.
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
