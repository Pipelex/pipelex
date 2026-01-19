import asyncio
import inspect
from typing import Literal, cast, get_type_hints

from pydantic import field_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs, TypedNamedStuffSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.exceptions import PipeRunError
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
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @field_validator("function_name", mode="before")
    @classmethod
    def validate_function_name(cls, function_name: str) -> str:
        function = func_registry.get_function(function_name)
        if not function:
            msg = f"Function '{function_name}' not found in registry"
            raise ValueError(msg)

        return_type = get_type_hints(function).get("return")

        if return_type is None:
            msg = f"Function '{function_name}' has no return type annotation"
            raise ValueError(msg)
        if not issubclass(return_type, StuffContent):
            msg = f"Function '{function_name}' return type {return_type} is not a subclass of StuffContent"
            raise TypeError(msg)
        return function_name

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        function = func_registry.get_required_function(self.function_name)
        return_type = get_type_hints(function).get("return")
        if return_type is None:
            msg = (
                f"PipeFunc '{self.code}' failed to validate output with library: The return type of the function is None. "
                "It should be a subclass of StuffContent."
            )
            raise TypeError(msg)
        if self.output.multiplicity and not issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is not a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.to_bundle_representation()}'. The return type of your function should be a subclass of ListContent."
            )
            raise TypeError(msg)
        if not self.output.multiplicity and issubclass(return_type, ListContent):
            msg = (
                f"PipeFunc '{self.code}' output multiplicity is '{self.output.multiplicity}', but the function '{self.function_name}' "
                f"return type {return_type} is a subclass of ListContent. The output of your PipeFunc is "
                f"'{self.output.concept.concept_ref}{self.output.to_bundle_representation()}' "
                f"when it should be '{self.output.concept.concept_ref}' (no multiplicity)."
            )
            raise TypeError(msg)

    @override
    async def _live_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeFuncOutput:
        log.verbose(f"Running PipeFunc with function '{self.function_name}'")
        function = func_registry.get_required_function(self.function_name)

        if inspect.iscoroutinefunction(function):
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
            concept=self.output.concept,
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
        function = func_registry.get_required_function(self.function_name)
        return_type = get_type_hints(function).get("return")
        if return_type is None:
            msg = f"Dry run of {self.type} '{self.code}' failed: The return type of the function is None. It should be a subclass of StuffContent."
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        # TODO: Support PipeFunc returning with multiplicity. Create an equivalent of TypedNamedInputRequirement for outputs.
        stuff_spec = TypedNamedStuffSpec(
            variable_name="mock_output",
            concept=ConceptFactory.make(
                concept_code=self.output.concept.code,
                domain_code="generic",
                description="Lorem Ipsum",
                structure_class_name=self.output.concept.structure_class_name,
            ),
            structure_class=return_type,
            multiplicity=False,
        )
        mock_content = WorkingMemoryFactory.create_mock_content(stuff_spec)

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
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

    @override
    async def _validate_before_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        function = func_registry.get_required_function(self.function_name)
        return_type = get_type_hints(function).get("return")
        # TODO: this should not happend ever. The correct way to do this would be to have a unit test making sure
        # that the FuncRegistry DOES CALL the 'is_eligible_function' function, and this function should be unit tested.
        if return_type is None:
            msg = f"Dry run failed for {self.type} '{self.code}': function '{self.function_name}' has no return type annotation"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
        if not issubclass(return_type, StuffContent):
            msg = (
                f"Dry run failed for pipe {self.type} '{self.code}': "
                f"function '{self.function_name}' return type {return_type} is not a subclass of StuffContent"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
