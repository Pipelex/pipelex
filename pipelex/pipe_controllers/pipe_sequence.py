from typing import List, Optional, Set

from typing_extensions import override

from pipelex import log
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeRunParamsError
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipeline.job_metadata import JobMetadata


class PipeSequence(PipeController):
    pipe_steps: List[SubPipe]

    @override
    def pipe_dependencies(self) -> Set[str]:
        return set(step.pipe_code for step in self.pipe_steps)

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        log.debug(f"run_pipe_direct: output_name={output_name}")
        pipe_run_params.push_pipe_layer(pipe_code=self.code)
        if pipe_run_params.is_multiple_output_required:
            raise PipeRunParamsError(
                f"PipeSequence does not suppport multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            )
        log.dev(f"{self.class_name} generating a '{self.output_concept_code}' named -> {output_name or 'unnamed'}")
        log.dev(f"self.pipe_steps:\n{self.pipe_steps}")

        if not self.output_concept_code:
            raise ValueError("No output concept code")

        current_memory = working_memory

        for step_index, step in enumerate(self.pipe_steps):
            step_run_params: PipeRunParams
            # only the last step should apply the final_stuff_code
            if step_index == len(self.pipe_steps) - 1:
                step_run_params = pipe_run_params.model_copy()
            else:
                step_run_params = pipe_run_params.model_copy(update=({"final_stuff_code": None}))
            pipe_output = await step.run(
                working_memory=current_memory,
                job_metadata=job_metadata,
                sub_pipe_run_params=step_run_params,
            )
            current_memory = pipe_output.working_memory

        return PipeOutput(
            working_memory=current_memory,
        )
