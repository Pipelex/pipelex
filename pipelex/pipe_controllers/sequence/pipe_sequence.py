from typing import Literal

from pydantic import field_validator
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError, PipeValidationErrorType
from pipelex.core.pipes.inputs.exceptions import PipeInputNotFoundError
from pipelex.core.pipes.inputs.input_requirements import InputRequirements
from pipelex.core.pipes.inputs.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.hub import get_concept_library, get_required_pipe
from pipelex.pipe_controllers.exceptions import PipeControllerOutputConceptMismatchError
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceValueError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.exceptions import PipeRunError, PipeRunParamsError
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
        The output of the pipe sequence should match the output of the last step.
        """
        last_step_pipe_code = self.sequential_sub_pipes[-1].pipe_code
        last_step_pipe = get_required_pipe(pipe_code=last_step_pipe_code)
        last_step_output_concept = last_step_pipe.output
        if not get_concept_library().is_compatible(tested_concept=last_step_output_concept, wanted_concept=self.output):
            msg = (
                f"PipeSequence concept mismatch: the output concept '{last_step_output_concept.concept_string}' "
                f"of the last step '{last_step_pipe_code}' of sequence pipe '{self.code}' "
                f"is not compatible with the output concept '{self.output.concept_string}' of the sequence."
            )
            raise PipeValidationError(
                message=msg,
                error_type=PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT,
                domain=self.domain,
                pipe_code=self.code,
                provided_concept_code=last_step_output_concept.concept_string,
                required_concept_codes=[self.output.concept_string],
            )

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputRequirements:
        if visited_pipes is None:
            visited_pipes = set()

        # If we've already visited this pipe, stop recursion
        if self.code in visited_pipes:
            return InputRequirementsFactory.make_empty()

        # Add this pipe to visited set for recursive calls
        visited_pipes_with_current = visited_pipes | {self.code}

        needed_inputs = InputRequirementsFactory.make_empty()
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
                        requirement = sub_pipe_needed_inputs.get_required_input_requirement(
                            variable_name=sequential_sub_pipe.batch_params.input_item_stuff_name
                        )
                    except PipeInputNotFoundError as exc:
                        msg = (
                            f"Batch input item named '{sequential_sub_pipe.batch_params.input_item_stuff_name}' is not "
                            f"in this PipeSequence '{self.code}' input requirements: {sub_pipe_needed_inputs}"
                        )
                        raise PipeSequenceValueError(msg) from exc
                    needed_inputs.add_requirement(
                        variable_name=sequential_sub_pipe.batch_params.input_list_stuff_name,
                        concept=requirement.concept,
                        multiplicity=True,
                    )
                    for input_name, requirement in sub_pipe_needed_inputs.items:
                        if input_name != sequential_sub_pipe.batch_params.input_item_stuff_name and input_name not in generated_outputs:
                            needed_inputs.add_requirement(input_name, requirement.concept, requirement.multiplicity)
            else:
                for input_name, requirement in sub_pipe_needed_inputs.items:
                    if input_name not in generated_outputs:
                        needed_inputs.add_requirement(input_name, requirement.concept, requirement.multiplicity)

            # Add this step's output to generated outputs
            if sequential_sub_pipe.output_name:
                generated_outputs.add(sequential_sub_pipe.output_name)
        return needed_inputs

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.sequential_sub_pipes}

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        pipe_run_params.push_pipe_layer(pipe_code=self.code)
        if pipe_run_params.is_multiple_output_required:
            msg = f"{self.__class__.__name__} does not support multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            raise PipeRunParamsError(msg)

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
        if not pipe_run_params.run_mode.is_dry:
            msg = f"PipeSequence._dry_run_controller_pipe() called with run_mode = {pipe_run_params.run_mode} in pipe {self.code}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode)
        # Verify the output of this pipe is matching the output of the last step.
        concept_of_last_step = get_required_pipe(pipe_code=self.sequential_sub_pipes[-1].pipe_code).output
        # if self.output.concept_string != concept_string_of_last_step:
        if not get_concept_library().is_compatible(tested_concept=concept_of_last_step, wanted_concept=self.output):
            msg = f"""PipeSequence concept mismatch:
the output concept '{concept_of_last_step.concept_string}' of the last step '{self.sequential_sub_pipes[-1].pipe_code}'
of sequence pipe '{self.code}' is not compatible with the output concept '{self.output.concept_string}' of the sequence.
"""
            raise PipeControllerOutputConceptMismatchError(
                message=msg, tested_concept=concept_of_last_step.concept_string, wanted_concept=self.output.concept_string
            )
        return await self._run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
