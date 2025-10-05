import asyncio
from typing import TYPE_CHECKING, Any, Literal

from pydantic import model_validator
from typing_extensions import override

from pipelex import log
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.input_requirements import InputRequirements
from pipelex.core.pipes.input_requirements_factory import InputRequirementsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import DryRunError, PipeDefinitionError, PipeRunParamsError, StaticValidationError, StaticValidationErrorType
from pipelex.hub import get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.pipe_run_params import PipeRunMode, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.types import Self

if TYPE_CHECKING:
    from collections.abc import Coroutine

    from pipelex.core.stuffs.stuff import Stuff
    from pipelex.core.stuffs.stuff_content import StuffContent


class PipeParallel(PipeController):
    type: Literal["PipeParallel"] = "PipeParallel"

    parallel_sub_pipes: list[SubPipe]
    add_each_output: bool
    combined_output: Concept | None

    @override
    def required_variables(self) -> set[str]:
        return set()

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

        for sub_pipe in self.parallel_sub_pipes:
            pipe = get_required_pipe(pipe_code=sub_pipe.pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes_with_current)
            if sub_pipe.batch_params:
                needed_inputs.add_requirement(
                    variable_name=sub_pipe.batch_params.input_list_stuff_name,
                    concept=pipe_needed_inputs.get_required_input_requirement(variable_name=sub_pipe.batch_params.input_item_stuff_name).concept,
                    multiplicity=True,
                )
                for input_name, requirement in pipe_needed_inputs.items:
                    if input_name != sub_pipe.batch_params.input_item_stuff_name:
                        needed_inputs.add_requirement(input_name, requirement.concept, requirement.multiplicity)
            else:
                for input_name, requirement in pipe_needed_inputs.items:
                    needed_inputs.add_requirement(input_name, requirement.concept, requirement.multiplicity)
        return needed_inputs

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        # Validate that either add_each_output or combined_output is set
        if not self.add_each_output and not self.combined_output:
            msg = f"PipeParallel'{self.code}'requires either add_each_output or combined_output to be set"
            raise PipeDefinitionError(msg)

        return self

    @override
    def validate_output(self):
        pass

    def _validate_inputs(self):
        """Validate that the inputs declared for this PipeParallel match what is actually needed."""
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
                extraneous_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE,
                    domain=self.domain,
                    pipe_code=self.code,
                    variable_names=[input_name],
                )
                match reactions.get(StaticValidationErrorType.EXTRANEOUS_INPUT_VARIABLE, default_reaction):
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
        return {sub_pipe.pipe_code for sub_pipe in self.parallel_sub_pipes}

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        """Run a list of pipes in parallel."""
        if not self.add_each_output and not self.combined_output:
            msg = "PipeParallel requires either add_each_output or combined_output to be set"
            raise PipeDefinitionError(msg)
        if pipe_run_params.final_stuff_code:
            log.debug(f"PipeBatch.run_pipe() final_stuff_code: {pipe_run_params.final_stuff_code}")
            pipe_run_params.final_stuff_code = None

        tasks: list[Coroutine[Any, Any, PipeOutput]] = []

        for sub_pipe in self.parallel_sub_pipes:
            tasks.append(
                sub_pipe.run_pipe(
                    calling_pipe_code=self.code,
                    job_metadata=job_metadata,
                    working_memory=working_memory.make_deep_copy(),
                    sub_pipe_run_params=pipe_run_params.make_deep_copy(),
                ),
            )

        pipe_outputs = await asyncio.gather(*tasks)

        output_stuff_content_items: list[StuffContent] = []
        output_stuffs: dict[str, Stuff] = {}
        output_stuff_contents: dict[str, StuffContent] = {}

        # TODO: refactor this to use a specific function for this that can also be used in dry run
        for output_index, pipe_output in enumerate(pipe_outputs):
            output_stuff = pipe_output.main_stuff
            sub_pipe_output_name = self.parallel_sub_pipes[output_index].output_name
            if not sub_pipe_output_name:
                msg = "PipeParallel requires a result specified for each parallel sub pipe"
                raise PipeDefinitionError(msg)
            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)
            output_stuff_content_items.append(output_stuff.content)
            if sub_pipe_output_name in output_stuffs:
                # TODO: check that at the blueprint / factory level
                msg = f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                raise PipeDefinitionError(msg)
            output_stuffs[sub_pipe_output_name] = output_stuff
            if sub_pipe_output_name in output_stuff_contents:
                # TODO: check that at the blueprint / factory level
                msg = f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                raise PipeDefinitionError(msg)
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content
            log.debug(f"PipeParallel '{self.code}': output_stuff_contents[{sub_pipe_output_name}]: {output_stuff_contents[sub_pipe_output_name]}")

        if self.combined_output:
            combined_output_stuff = StuffFactory.combine_stuffs(
                concept=self.combined_output,
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
        """Dry run implementation for PipeParallel.
        Validates that all required inputs are present and that all parallel sub-pipes can be dry run.
        """
        log.debug(f"PipeParallel: dry run controller pipe: {self.code}")
        if pipe_run_params.run_mode != PipeRunMode.DRY:
            msg = f"PipeSequence._dry_run_controller_pipe() called with run_mode = {pipe_run_params.run_mode} in pipe {self.code}"
            raise PipeRunParamsError(msg)

        # 1. Validate that all required inputs are present in the working memory
        needed_inputs = self.needed_inputs()
        missing_input_names: list[str] = []

        for named_input_requirement in needed_inputs.named_input_requirements:
            if not working_memory.get_optional_stuff(named_input_requirement.variable_name):
                missing_input_names.append(named_input_requirement.variable_name)

        if missing_input_names:
            msg = f"Dry run failed: missing required inputs: {missing_input_names}"
            log.error(f"Dry run failed: missing required inputs: {missing_input_names}")
            raise DryRunError(
                message=msg,
                missing_inputs=missing_input_names,
                pipe_code=self.code,
            )

        # 2. Validate that all sub-pipes exist
        for sub_pipe in self.parallel_sub_pipes:
            try:
                get_required_pipe(pipe_code=sub_pipe.pipe_code)
            except Exception as exc:
                msg = f"PipeParallel'{self.code}'sub-pipe '{sub_pipe.pipe_code}' not found"
                raise PipeDefinitionError(msg) from exc

        # 3. Run all sub-pipes in dry mode
        tasks: list[Coroutine[Any, Any, PipeOutput]] = []

        for sub_pipe in self.parallel_sub_pipes:
            tasks.append(
                sub_pipe.run_pipe(
                    calling_pipe_code=self.code,
                    job_metadata=job_metadata,
                    working_memory=working_memory.make_deep_copy(),
                    sub_pipe_run_params=pipe_run_params.make_deep_copy(),
                ),
            )

        try:
            pipe_outputs = await asyncio.gather(*tasks)
        except Exception as exc:
            msg = f"Dry run failed: parallel sub-pipe execution failed: {exc}"
            log.error(msg)
            raise DryRunError(
                message=msg,
                missing_inputs=[],
                pipe_code=self.code,
            ) from exc

        # 4. Process outputs as in the regular run
        output_stuffs: dict[str, Stuff] = {}
        output_stuff_contents: dict[str, StuffContent] = {}

        for output_index, pipe_output in enumerate(pipe_outputs):
            output_stuff = pipe_output.main_stuff
            sub_pipe_output_name = self.parallel_sub_pipes[output_index].output_name
            if not sub_pipe_output_name:
                msg = f"Dry run failed for pipe '{self.code}' (PipeParallel): sub-pipe output name not specified"
                raise DryRunError(
                    message=msg,
                    missing_inputs=[],
                    pipe_code=self.code,
                )

            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)

            if sub_pipe_output_name in output_stuffs:
                msg = f"Dry run failed for pipe '{self.code}' (PipeParallel): duplicate output name '{sub_pipe_output_name}'"
                raise DryRunError(
                    message=msg,
                    missing_inputs=[],
                    pipe_code=self.code,
                )

            output_stuffs[sub_pipe_output_name] = output_stuff
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content

        # 5. Handle combined output if specified
        if self.combined_output:
            combined_output_stuff = StuffFactory.combine_stuffs(
                concept=self.combined_output,
                stuff_contents=output_stuff_contents,
                name=output_name,
            )
            working_memory.set_new_main_stuff(
                stuff=combined_output_stuff,
                name=output_name,
            )
        return PipeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
