from typing import Optional

from pydantic import BaseModel

from pipelex import log, pretty_print
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import BatchParams, PipeOutputMultiplicity, PipeRunParams
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeInputError, WorkingMemoryStuffNotFoundError
from pipelex.hub import get_pipe_router, get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.pipe_batch import PipeBatch
from pipelex.pipe_controllers.pipe_condition import PipeCondition
from pipelex.pipeline.job_metadata import JobMetadata


# TODO: decide if SubPipe should be a PipeAbstract (it's probably the case)
# TODO: update job metadata
class SubPipe(BaseModel):
    pipe_code: str
    output_name: Optional[str] = None
    output_multiplicity: Optional[PipeOutputMultiplicity] = None
    batch_params: Optional[BatchParams] = None

    async def run(
        self,
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        sub_pipe_run_params: PipeRunParams,
    ) -> PipeOutput:
        """Run a single operation self."""
        log.debug(f"SubPipe {self.pipe_code} to generate {self.output_name}")
        # step_run_params.push_pipe_code(pipe_code=self.pipe_code)
        if self.output_multiplicity:
            sub_pipe_run_params.output_multiplicity = self.output_multiplicity
        pipe = get_required_pipe(pipe_code=self.pipe_code)
        pipe_output: PipeOutput
        sub_pipe_run_params.batch_params = self.batch_params
        if batch_params := self.batch_params:
            input_list_stuff = working_memory.get_stuff(name=batch_params.input_list_stuff_name)
            input_concept_code = input_list_stuff.concept_code
            output_concept_code = pipe.output_concept_code
            pipe_batch = PipeBatch(
                domain=pipe.domain,
                code=self.pipe_code,
                input_concept_code=input_concept_code,
                output_concept_code=output_concept_code,
                branch_pipe_code=self.pipe_code,
            )
            pipe_output = await pipe_batch.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=sub_pipe_run_params,
                output_name=self.output_name,
            )
        elif isinstance(pipe, PipeCondition):
            pipe_output = await get_pipe_router().run_pipe_code(
                pipe_code=self.pipe_code,
                job_metadata=job_metadata,
                working_memory=working_memory,
                output_name=self.output_name,
                pipe_run_params=sub_pipe_run_params,
            )
        else:
            required_variables = pipe.required_variables()
            log.debug(required_variables, title=f"Required variables for {self.pipe_code}")
            required_stuff_names = set([required_variable for required_variable in required_variables if not required_variable.startswith("_")])
            try:
                required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
            except WorkingMemoryStuffNotFoundError as exc:
                error_details = f"sub_pipe '{self.pipe_code}', stack: {sub_pipe_run_params.pipe_layers}, required_variables: {required_variables}"
                raise PipeInputError(f"Some required stuff(s) not found - {error_details}") from exc
            log.debug(required_stuffs, title=f"Required stuffs for {self.pipe_code}")
            pipe_output = await get_pipe_router().run_pipe_code(
                pipe_code=self.pipe_code,
                job_metadata=job_metadata,
                working_memory=working_memory,
                output_name=self.output_name,
                pipe_run_params=sub_pipe_run_params,
            )
            new_output_stuff = pipe_output.main_stuff
            for stuff in required_stuffs:
                get_pipeline_tracker().add_pipe_step(
                    from_stuff=stuff,
                    to_stuff=new_output_stuff,
                    pipe_code=self.pipe_code,
                    pipe_layer=sub_pipe_run_params.pipe_layers,
                    comment="SubPipe on required_stuff",
                )
        pretty_print(pipe_output.main_stuff, title=f"Pipe output for {self.pipe_code}")
        return pipe_output
