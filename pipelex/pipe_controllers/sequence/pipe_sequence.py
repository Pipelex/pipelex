from typing import Literal

from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.exceptions import (
    PipeRunParamsError,
    StaticValidationError,
    StaticValidationErrorType,
)
from pipelex.hub import get_required_pipe
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sequence.exceptions import PipeSequenceError
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.types import Self


class PipeSequence(PipeController):
    type: Literal["PipeSequence"] = "PipeSequence"
    sequential_sub_pipes: list[SubPipe]

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
                    needed_inputs.add_requirement(
                        variable_name=sequential_sub_pipe.batch_params.input_list_stuff_name,
                        concept=sub_pipe_needed_inputs.get_required_input_requirement(
                            variable_name=sequential_sub_pipe.batch_params.input_item_stuff_name,
                        ).concept,
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
    def required_variables(self) -> set[str]:
        return set()

    @override
    def validate_output(self):
        """Validate the output for the pipe sequence.
        The output of the pipe sequence should match the output of the last step.
        """
        last_step_output_pipe = get_required_pipe(pipe_code=self.sequential_sub_pipes[-1].pipe_code)
        if self.output.concept_string != last_step_output_pipe.output.concept_string:
            msg = (
                f"The output concept code '{self.output.concept_string}' of the pipe '{self.code}' is "
                f"not matching the output concept code '{last_step_output_pipe.output.concept_string}' "
                f"of the last step '{self.sequential_sub_pipes[-1].pipe_code}'",
            )
            raise PipeSequenceError(msg)

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        if len(self.sequential_sub_pipes) == 0:
            msg = f"Pipe'{self.code}'(PipeSequence) must have at least 1 step"
            raise ValueError(msg)
        return self

    def _validate_output_multiplicity_support(self, pipe_run_params: PipeRunParams) -> None:
        """Validate that the pipe supports the requested output multiplicity."""
        if pipe_run_params.is_multiple_output_required:
            msg = f"{self.__class__.__name__} does not support multiple outputs, got output_multiplicity = {pipe_run_params.output_multiplicity}"
            raise PipeRunParamsError(msg)

    def _validate_inputs(self):
        """Validate that the inputs declared for this PipeSequence match what is actually needed."""
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions

        the_needed_inputs = self.needed_inputs()

        # Check all required variables are in the inputs
        for named_input_requirement in the_needed_inputs.named_input_requirements:
            if named_input_requirement.variable_name not in self.inputs.variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[named_input_requirement.variable_name],
                    required_concept_codes=[named_input_requirement.concept.code],
                )
                match reactions.get(StaticValidationErrorType.MISSING_INPUT_VARIABLE, default_reaction):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(missing_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise missing_input_var_error

        # Check that all declared inputs are actually needed
        for input_name in self.inputs.variables:
            if input_name not in the_needed_inputs.required_names:
                log.debug(f"the_needed_inputs.required_names: {the_needed_inputs.required_names}")
                extraneous_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                )
                match reactions.get(
                    StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    default_reaction,
                ):
                    case StaticValidationReaction.IGNORE:
                        pass
                    case StaticValidationReaction.LOG:
                        log.error(extraneous_input_var_error.desc())
                    case StaticValidationReaction.RAISE:
                        raise extraneous_input_var_error

    @override
    def validate_with_libraries(self):
        """Perform full validation after all libraries are loaded.
        This is called after all pipes and concepts are available.
        """
        self._validate_inputs()

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
        self._validate_output_multiplicity_support(pipe_run_params)

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
            raise PipeRunParamsError(msg)
        # Verify the output of this pipe is matching the output of the last step.
        concept_string_of_last_step = get_required_pipe(pipe_code=self.sequential_sub_pipes[-1].pipe_code).output.concept_string
        if self.output.concept_string != concept_string_of_last_step:
            msg = (
                f"The output concept code '{self.output.concept_string}' of the pipe '{self.code}' is "
                f"not matching the output concept code '{concept_string_of_last_step}' of the last step '{self.sequential_sub_pipes[-1].pipe_code}'"
            )
            raise ValueError(msg)
        return await self._run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
