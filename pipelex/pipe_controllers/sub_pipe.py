from pydantic import BaseModel

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.list_content import ListContent
from pipelex.exceptions import PipeInputError, PipeInputNotFoundError, WorkingMemoryStuffNotFoundError
from pipelex.hub import get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_factory import PipeBatchFactory
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class SubPipe(BaseModel):
    pipe_code: str
    output_name: str | None = None
    output_multiplicity: VariableMultiplicity | None = None
    batch_params: BatchParams | None = None
    concept_codes_from_the_same_domain: list[str] | None = None

    async def run_pipe(
        self,
        calling_pipe_code: str,
        working_memory: WorkingMemory,
        job_metadata: JobMetadata,
        sub_pipe_run_params: PipeRunParams,
    ) -> PipeOutput:
        """Run or dry run a single operation self."""
        if self.output_multiplicity:
            sub_pipe_run_params.output_multiplicity = self.output_multiplicity
        sub_pipe_run_params.batch_params = self.batch_params

        sub_pipe = get_required_pipe(pipe_code=self.pipe_code)

        # Case 1: Batch processing
        if batch_params := self.batch_params:
            try:
                working_memory.get_typed_object_or_attribute(name=batch_params.input_list_stuff_name, wanted_type=ListContent)
            except WorkingMemoryStuffNotFoundError as exc:
                msg = (
                    f"Input list stuff named '{batch_params.input_list_stuff_name}' required by sub_pipe '{self.pipe_code}' "
                    f"of pipe '{calling_pipe_code}' not found in working memory: {exc}"
                )
                raise PipeInputError(
                    message=msg, pipe_code=self.pipe_code, variable_name=batch_params.input_list_stuff_name, concept_code=None
                ) from exc

            try:
                item_stuff_requirement = sub_pipe.inputs.get_required_input_requirement(variable_name=batch_params.input_item_stuff_name)
            except PipeInputNotFoundError as exc:
                msg = (
                    f"Batch input item named '{batch_params.input_item_stuff_name}' from '{calling_pipe_code}' is not "
                    f"in SubPipe '{self.pipe_code}' input requirements: {sub_pipe.inputs}"
                )
                raise PipeInputError(
                    message=msg, pipe_code=self.pipe_code, variable_name=batch_params.input_item_stuff_name, concept_code=None
                ) from exc
            pipe_batch_blueprint = PipeBatchBlueprint(
                description=f"Batch processing for {self.pipe_code}",
                branch_pipe_code=self.pipe_code,
                output=sub_pipe.output.code,
                input_list_name=batch_params.input_list_stuff_name,
                input_item_name=batch_params.input_item_stuff_name,
                inputs={
                    batch_params.input_list_stuff_name: item_stuff_requirement.concept.concept_string,
                },
            )

            pipe_batch = PipeBatchFactory.make_from_blueprint(
                domain=sub_pipe.domain,
                pipe_code=self.pipe_code,
                blueprint=pipe_batch_blueprint,
                concept_codes_from_the_same_domain=self.concept_codes_from_the_same_domain,
            )
            pipe_output = await pipe_batch.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=sub_pipe_run_params,
                output_name=self.output_name,
            )
        # Case 2: Condition processing
        elif isinstance(sub_pipe, PipeCondition):
            pipe_output = await sub_pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=sub_pipe_run_params,
                output_name=self.output_name,
            )
        else:
            # Case 3: Normal processing
            required_variables = sub_pipe.required_variables()
            required_stuff_names = {req_var for req_var in required_variables if not req_var.startswith("_")}
            try:
                required_stuffs = working_memory.get_stuffs(names=required_stuff_names)
            except WorkingMemoryStuffNotFoundError as exc:
                sub_pipe_path = [*sub_pipe_run_params.pipe_stack, self.pipe_code]
                sub_pipe_path_str = ".".join(sub_pipe_path)
                error_details = f"SubPipe '{sub_pipe_path_str}', required_variables: {required_variables}, missing: '{exc.variable_name}'"
                msg = f"Some required stuff(s) not found: {error_details}"
                raise PipeInputError(message=msg, pipe_code=self.pipe_code, variable_name=exc.variable_name, concept_code=None) from exc
            log.verbose(required_stuffs, title=f"Required stuffs for {self.pipe_code}")
            pipe_output = await sub_pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=working_memory,
                pipe_run_params=sub_pipe_run_params,
                output_name=self.output_name,
            )
            if new_output_stuff := pipe_output.working_memory.get_optional_main_stuff():
                for stuff in required_stuffs:
                    get_pipeline_tracker().add_pipe_step(
                        from_stuff=stuff,
                        to_stuff=new_output_stuff,
                        pipe_code=self.pipe_code,
                        pipe_layer=sub_pipe_run_params.pipe_layers,
                        comment="SubPipe on required_stuff",
                    )
        return pipe_output
