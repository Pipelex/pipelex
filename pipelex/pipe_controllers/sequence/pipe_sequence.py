from typing import Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.variable_multiplicity import is_multiplicity_compatible
from pipelex.hub import get_concept_library, get_required_pipe
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceValueError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata


class PipeSequence(PipeController):
    type: Literal["PipeSequence"] = "PipeSequence"
    sequential_sub_pipes: list[SubPipe]

    @override
    def required_variables(self) -> set[str]:
        return set()

    @field_validator("sequential_sub_pipes", mode="after")
    @classmethod
    def validate_sequential_sub_pipes(cls, value: list[SubPipe]) -> list[SubPipe]:
        if not value:
            msg = f"PipeSequence '{cls.code}' requires at least one sub-pipe"
            raise ValueError(msg)
        return value

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
        """Validate the output for the pipe sequence.

        The output of the pipe sequence should match the output of the last step,
        both in terms of concept compatibility and multiplicity.
        """
        last_step_pipe = get_required_pipe(pipe_code=self.sequential_sub_pipes[-1].pipe_code)

        # Check concept compatibility
        if not get_concept_library().is_compatible(tested_concept=last_step_pipe.output.concept, wanted_concept=self.output.concept):
            msg = (
                f"PipeSequence concept mismatch: the output concept '{last_step_pipe.output.concept.concept_ref}' "
                f"of the last step '{last_step_pipe.code}' of sequence pipe '{self.code}' "
                f"is not compatible with the output concept '{self.output.concept.concept_ref}' of the sequence."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_pipe.output.concept.concept_ref,
                required_concept_codes=[self.output.concept.concept_ref],
            )

        last_sub_pipe = self.sequential_sub_pipes[-1]
        effective_last_step_output_multiplicity = last_sub_pipe.output_multiplicity
        if not effective_last_step_output_multiplicity:
            effective_last_step_output_multiplicity = get_required_pipe(pipe_code=last_sub_pipe.pipe_code).output.multiplicity

        # Check multiplicity compatibility
        if not is_multiplicity_compatible(
            source_multiplicity=effective_last_step_output_multiplicity,
            target_multiplicity=self.output.multiplicity,
        ):
            msg = (
                f"PipeSequence output multiplicity mismatch: the sequence '{self.code}' declares "
                f"output multiplicity={self.output.multiplicity}, but the last step '{last_step_pipe.code}' "
                f"has output multiplicity={effective_last_step_output_multiplicity}. They are not compatible. "
                "Update one of them to match the other."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY,
                domain_code=self.domain_code,
                pipe_code=self.code,
                provided_concept_code=last_step_pipe.output.concept.concept_ref,
                required_concept_codes=[self.output.concept.concept_ref],
            )

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.code in visited_pipes:
            return InputStuffSpecsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.code}

        needed_inputs = InputStuffSpecsFactory.make_empty()
        generated_outputs: set[str] = set()

        for sequential_sub_pipe in self.sequential_sub_pipes:
            sub_pipe = get_required_pipe(pipe_code=sequential_sub_pipe.pipe_code)
            # Use the centralized recursion detection
            sub_pipe_needed_inputs = sub_pipe.needed_inputs(visited_pipes_with_current)

            if isinstance(sub_pipe, PipeParallel) and sub_pipe.add_each_output:
                for sub_parallel_pipe in sub_pipe.parallel_sub_pipes:
                    if (sub_pipe.add_each_output and sub_parallel_pipe.output_name) or sub_parallel_pipe.output_name:
                        generated_outputs.add(sub_parallel_pipe.output_name)

            if sequential_sub_pipe.batch_params:
                if sequential_sub_pipe.batch_params.input_list_stuff_name not in generated_outputs:
                    try:
                        stuff_spec = sub_pipe_needed_inputs.get_required_stuff_spec(
                            variable_name=sequential_sub_pipe.batch_params.input_item_stuff_name
                        )
                    except InputStuffSpecNotFoundError as exc:
                        msg = (
                            f"Batch input item named '{sequential_sub_pipe.batch_params.input_item_stuff_name}' is not "
                            f"in this PipeSequence '{self.code}' input requirements: {sub_pipe_needed_inputs}"
                        )
                        raise PipeSequenceValueError(msg) from exc
                    needed_inputs.add_stuff_spec(
                        variable_name=sequential_sub_pipe.batch_params.input_list_stuff_name,
                        concept=stuff_spec.concept,
                        multiplicity=True,
                    )
                    for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                        if input_name != sequential_sub_pipe.batch_params.input_item_stuff_name and input_name not in generated_outputs:
                            needed_inputs.add_stuff_spec(input_name, stuff_spec.concept, stuff_spec.multiplicity)
            else:
                for input_name, stuff_spec in sub_pipe_needed_inputs.items:
                    if input_name not in generated_outputs:
                        needed_inputs.add_stuff_spec(input_name, stuff_spec.concept, stuff_spec.multiplicity)

            # Add this step's output to generated outputs
            if sequential_sub_pipe.output_name:
                generated_outputs.add(sequential_sub_pipe.output_name)

        return needed_inputs

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.sequential_sub_pipes}

    @override
    async def _live_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        evolving_memory = working_memory

        for sub_pipe_index, sub_pipe in enumerate(self.sequential_sub_pipes):
            # Only the last step should apply the final_stuff_code
            if sub_pipe_index == len(self.sequential_sub_pipes) - 1:
                sub_pipe_run_params = pipe_run_params.model_copy()
            else:
                sub_pipe_run_params = pipe_run_params.model_copy(update=({"final_stuff_code": None}))
            pipe_output = await sub_pipe.run_pipe(
                calling_pipe_code=self.code,
                working_memory=evolving_memory,
                job_metadata=job_metadata,
                sub_pipe_run_params=sub_pipe_run_params,
            )
            evolving_memory = pipe_output.working_memory
        return PipeOutput(
            working_memory=evolving_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        return await self._live_run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )

    @override
    async def _validate_before_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
