from typing import List, Optional, Set

from typing_extensions import override

from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeRunParamsError
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipeline.job_metadata import JobMetadata


class PipeSequence(PipeController):
    sequential_sub_pipes: List[SubPipe]

    @override
    def pipe_dependencies(self) -> Set[str]:
        return set(sub_pipe.pipe_code for sub_pipe in self.sequential_sub_pipes)

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_layer(pipe_code=self.code)
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeSequence does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )

        current_memory = working_memory

        for sub_pipe_index, sub_pipe in enumerate(self.sequential_sub_pipes):
            sub_pipe_run_params: PipeRunParams
            # only the last step should apply the final_stuff_code
            if sub_pipe_index == len(self.sequential_sub_pipes) - 1:
                sub_pipe_run_params = pipe_run_params.model_copy()
            else:
                sub_pipe_run_params = pipe_run_params.model_copy(update=({"final_stuff_code": None}))
            pipe_output = await sub_pipe.run(
                calling_pipe_code=self.code,
                working_memory=current_memory,
                job_metadata=job_metadata,
                sub_pipe_run_params=sub_pipe_run_params,
            )
            current_memory = pipe_output.working_memory

        return PipeOutput(
            working_memory=current_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
