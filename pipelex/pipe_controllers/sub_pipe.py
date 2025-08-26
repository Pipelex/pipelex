from typing import List, Optional

from pydantic import BaseModel

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_input_spec_blueprint import InputRequirementBlueprint
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import BatchParams, PipeOutputMultiplicity, PipeRunMode, PipeRunParams
from pipelex.exceptions import PipeInputError, WorkingMemoryStuffNotFoundError
from pipelex.hub import get_pipe_router, get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_factory import PipeBatchFactory
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipeline.job_metadata import JobMetadata


class SubPipe(BaseModel):
    pipe_code: str
    output_name: Optional[str] = None
    output_multiplicity: Optional[PipeOutputMultiplicity] = None
    batch_params: Optional[BatchParams] = None
    concept_codes_from_the_same_domain: Optional[List[str]] = None

    async def run_pipe(
        self,
        calling_pipe_code: str,
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        sub_pipe_run_params: PipeRunParams,
    ) -> PipeOutput:
        """Run or dry run a single operation self."""
        log.debug(f"SubPipe {self.pipe_code} to generate {self.output_name}")
        if self.output_multiplicity:
            sub_pipe_run_params.output_multiplicity = self.output_multiplicity
        sub_pipe_run_params.batch_params = self.batch_params

        sub_pipe = get_required_pipe(pipe_code=self.pipe_code)
        pipe_output: PipeOutput

        # Case 1: Batch processing
        if batch_params := self.batch_params:
            try:
                input_list_stuff = working_memory.get_stuff(name=batch_params.input_list_stuff_name)
            except WorkingMemoryStuffNotFoundError as exc:
                raise PipeInputError(
                    f"Input list stuff named '{batch_params.input_list_stuff_name}' required by sub_pipe '{self.pipe_code}' "
                    f"of pipe '{calling_pipe_code}' not found in working memory: {exc}"
                ) from exc

            sub_pipe.inputs.add_requirement(variable_name=batch_params.input_list_stuff_name, concept=input_list_stuff.concept)

            # Create blueprint for PipeBatch
            pipe_batch_blueprint = PipeBatchBlueprint(
                definition=f"Batch processing for {self.pipe_code}",
                branch_pipe_code=self.pipe_code,
                output=sub_pipe.output.code,
                input_list_name=batch_params.input_list_stuff_name,
                input_item_name=batch_params.input_item_stuff_name,
                # inputs should be of type: Dict[str, InputRequirementBlueprint]
                inputs={
                    batch_params.input_item_stuff_name: InputRequirementBlueprint(
                        concept=sub_pipe.inputs.root[batch_params.input_item_stuff_name].concept.concept_string
                    ),
                },
            )

            pipe_batch = PipeBatchFactory.make_from_blueprint(
                domain=sub_pipe.domain,
                pipe_code=self.pipe_code,
                blueprint=pipe_batch_blueprint,
                concept_codes_from_the_same_domain=self.concept_codes_from_the_same_domain,
            )
            # This is the only line that changes between run and dry_run
            if sub_pipe_run_params.run_mode == PipeRunMode.DRY:
                sub_pipe_run_params.run_mode = PipeRunMode.DRY
                pipe_output = await pipe_batch.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                )
            else:
                sub_pipe_run_params.run_mode = PipeRunMode.LIVE
                pipe_output = await pipe_batch.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                )
        # Case 2: Condition processing
        elif isinstance(sub_pipe, PipeCondition):
            # This is the only line that changes between run and dry_run
            if sub_pipe_run_params.run_mode == PipeRunMode.DRY:
                sub_pipe_run_params.run_mode = PipeRunMode.DRY
                pipe_output = await sub_pipe.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                )
            else:
                sub_pipe_run_params.run_mode = PipeRunMode.LIVE
                pipe_output = await get_pipe_router().run_pipe_code(
                    pipe_code=self.pipe_code,
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    output_name=self.output_name,
                    pipe_run_params=sub_pipe_run_params,
                )
        else:
            # Case 3: Normal processing
            required_variables = sub_pipe.required_variables()
            log.debug(required_variables, title=f"Required variables for {self.pipe_code}")
            required_stuff_names = set([required_variable for required_variable in required_variables if not required_variable.startswith("_")])
            try:
                required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
            except WorkingMemoryStuffNotFoundError as exc:
                sub_pipe_path = sub_pipe_run_params.pipe_layers + [self.pipe_code]
                sub_pipe_path_str = ".".join(sub_pipe_path)
                error_details = f"SubPipe '{sub_pipe_path_str}', required_variables: {required_variables}, missing: '{exc.variable_name}'"
                raise PipeInputError(f"Some required stuff(s) not found: {error_details}") from exc
            log.verbose(required_stuffs, title=f"Required stuffs for {self.pipe_code}")
            # This is the only line that changes between run and dry_run
            if sub_pipe_run_params.run_mode == PipeRunMode.DRY:
                sub_pipe_run_params.run_mode = PipeRunMode.DRY
                pipe_output = await sub_pipe.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=working_memory,
                    pipe_run_params=sub_pipe_run_params,
                    output_name=self.output_name,
                )
            else:
                sub_pipe_run_params.run_mode = PipeRunMode.LIVE
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
        return pipe_output
