from typing import List, Optional, Set, cast, get_type_hints

from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec, TypedNamedInputRequirement
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import PipeRunParams
from pipelex.core.stuffs.stuff_content import ListContent, StuffContent, TextContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import DryRunError
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.func_registry import func_registry


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator):
    function_name: str

    @override
    def required_variables(self) -> Set[str]:
        return set()

    @override
    def needed_inputs(self) -> PipeInputSpec:
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
        output_name: Optional[str] = None,
    ) -> PipeFuncOutput:
        log.debug(f"Applying function '{self.function_name}'")

        function = func_registry.get_required_function(self.function_name)
        if not callable(function):
            raise ValueError(f"Function '{self.function_name}' is not callable")

        func_output_object = function(working_memory=working_memory)
        the_content: StuffContent
        if isinstance(func_output_object, StuffContent):
            the_content = func_output_object
        elif isinstance(func_output_object, list):
            func_result_list = cast(List[StuffContent], func_output_object)
            the_content = ListContent(items=func_result_list)
        elif isinstance(func_output_object, str):
            the_content = TextContent(text=func_output_object)
        else:
            raise ValueError(f"Function '{self.function_name}' must return a StuffContent or a list, got {type(func_output_object)}")

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeFuncOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
        return pipe_output

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.debug(f"Dry run for PipeFunc '{self.function_name}'")

        function = func_registry.get_required_function(self.function_name)
        if not callable(function):
            raise ValueError(f"Function '{self.function_name}' is not callable")

        # Check that all needed inputs are present in working memory
        needed_inputs = self.needed_inputs()
        for input_name, _ in needed_inputs.items:
            if input_name not in working_memory.root:
                raise DryRunError(
                    f"Required input '{input_name}' not found in working memory for function '{self.function_name}' in pipe '{self.code}'"
                )

        try:
            return_type = get_type_hints(function).get("return")

            if return_type is None:
                raise DryRunError(f"Function '{self.function_name}' has no return type annotation")
            else:
                if not issubclass(return_type, StuffContent):
                    raise ValueError(f"Function '{self.function_name}' return type {return_type} is not a subclass of StuffContent")

                requirement = TypedNamedInputRequirement(
                    variable_name="mock_output",
                    concept=ConceptFactory.make(
                        concept_code=f"{return_type.__name__}",
                        domain="generic",
                        definition="Lorem Ipsum",
                        structure_class_name=return_type.__name__,
                    ),
                    structure_class=return_type,
                    multiplicity=False,
                )
                mock_content = WorkingMemoryFactory.create_mock_content(requirement)

        except Exception as exc:
            raise DryRunError(f"Failed to get type hints for function '{self.function_name}' in pipe '{self.code}': {exc}")

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
