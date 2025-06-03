from typing import List, Optional, cast

from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff_content import ListContent, StuffContent, TextContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.func_registry import func_registry


class PipeFuncOutput(PipeOutput):
    pass


class PipeFunc(PipeOperator):
    function_name: str

    @override
    async def _run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeFuncOutput:
        if not self.output_concept_code:
            raise ValueError("PipeFunc should have a non-None output_concept_code")

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
            concept_code=self.output_concept_code,
            content=the_content,
        )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        pipe_output = PipeFuncOutput(
            working_memory=working_memory,
        )
        return pipe_output
