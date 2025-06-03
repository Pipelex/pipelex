import asyncio
from typing import Any, Coroutine, Dict, List, Optional, Set

from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import StuffContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError
from pipelex.hub import get_pipeline_tracker
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipeline.job_metadata import JobMetadata


class PipeParallel(PipeController):
    """Runs a list of pipes in parallel to produce a list of results."""

    parallel_sub_pipes: List[SubPipe]
    add_each_output: bool
    combined_output: Optional[str]

    @override
    def pipe_dependencies(self) -> Set[str]:
        return set(sub_pipe.pipe_code for sub_pipe in self.parallel_sub_pipes)

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """
        Run a list of pipes in parallel.
        """
        if not self.add_each_output and not self.combined_output:
            raise PipeDefinitionError("PipeParallel requires either add_each_output or combined_output to be set")
        if pipe_run_params.final_stuff_code:
            log.debug(f"PipeBatch.run_pipe() final_stuff_code: {pipe_run_params.final_stuff_code}")
            pipe_run_params.final_stuff_code = None

        tasks: List[Coroutine[Any, Any, PipeOutput]] = []

        for parallel_sub_pipe in self.parallel_sub_pipes:
            tasks.append(
                parallel_sub_pipe.run(
                    job_metadata=job_metadata,
                    working_memory=working_memory.make_deep_copy(),
                    sub_pipe_run_params=pipe_run_params,
                )
            )

        pipe_outputs = await asyncio.gather(*tasks)

        output_stuff_content_items: List[StuffContent] = []
        output_stuffs: Dict[str, Stuff] = {}
        output_stuff_contents: Dict[str, StuffContent] = {}

        for output_index, pipe_output in enumerate(pipe_outputs):
            output_stuff = pipe_output.main_stuff
            sub_pipe_output_name = self.parallel_sub_pipes[output_index].output_name
            if not sub_pipe_output_name:
                raise PipeDefinitionError("PipeParallel requires a result specified for each parallel sub pipe")
            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)
            output_stuff_content_items.append(output_stuff.content)
            if sub_pipe_output_name in output_stuffs:
                # TODO: check that at the blueprint / factory level
                raise PipeDefinitionError(
                    f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                )
            output_stuffs[sub_pipe_output_name] = output_stuff
            if sub_pipe_output_name in output_stuff_contents:
                # TODO: check that at the blueprint / factory level
                raise PipeDefinitionError(
                    f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                )
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content
        if combined_output := self.combined_output:
            combined_output_stuff = StuffFactory.combine_stuffs(
                concept_code=combined_output,
                stuff_contents=output_stuff_contents,
                name=output_name,
            )
            working_memory.set_new_main_stuff(
                stuff=combined_output_stuff,
                name=output_name,
            )
            for stuff in output_stuffs.values():
                get_pipeline_tracker().add_aggregate_step(
                    from_stuff=stuff,
                    to_stuff=combined_output_stuff,
                    pipe_layer=pipe_run_params.pipe_layers,
                    comment="PipeParallel on output_stuffs",
                )
        return PipeOutput(
            working_memory=working_memory,
        )
