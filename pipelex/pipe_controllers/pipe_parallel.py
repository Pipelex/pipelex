import asyncio
from typing import Any, Coroutine, Dict, List, Optional, Set, cast

from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.config import StaticValidationReaction, get_config
from pipelex.core.pipe_input_spec import PipeInputSpec
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeRunParams
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import StuffContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeDefinitionError, StaticValidationError, StaticValidationErrorType
from pipelex.hub import get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipeline.job_metadata import JobMetadata


class PipeParallel(PipeController):
    """Runs a list of pipes in parallel to produce a list of results."""

    parallel_sub_pipes: List[SubPipe]
    add_each_output: bool
    combined_output: Optional[str]

    def needed_inputs(self, _visited_pipes: Optional[Set[str]] = None) -> PipeInputSpec:
        """
        Calculate the inputs needed by this PipeParallel.
        This is the inputs needed by ALL parallel sub-pipes since they all run simultaneously.
        """
        if _visited_pipes is None:
            _visited_pipes = set()

        # Prevent infinite recursion
        if self.code in _visited_pipes:
            return PipeInputSpec()
        _visited_pipes.add(self.code)

        try:
            needed_inputs = PipeInputSpec()

            for sub_pipe in self.parallel_sub_pipes:
                pipe = get_required_pipe(pipe_code=sub_pipe.pipe_code)

                # Get the inputs needed by this parallel pipe
                pipe_needed_inputs: PipeInputSpec
                if hasattr(pipe, "needed_inputs") and callable(getattr(pipe, "needed_inputs")):
                    needed_inputs_method = getattr(pipe, "needed_inputs")
                    if pipe.__class__.__name__ in ("PipeSequence", "PipeCondition", "PipeParallel"):
                        pipe_needed_inputs = cast(PipeInputSpec, needed_inputs_method(_visited_pipes=_visited_pipes.copy()))
                    else:
                        pipe_needed_inputs = cast(PipeInputSpec, needed_inputs_method())
                else:
                    # Fallback for pipes without needed_inputs method
                    pipe_needed_inputs = pipe.inputs

                # Handle batching: if this sub_pipe has batch_params, exclude the batch_as input
                # since it's provided by the batching mechanism
                if sub_pipe.batch_params:
                    batch_as_input = sub_pipe.batch_params.input_item_stuff_name
                    # Create a new PipeInputSpec without the batch_as input
                    filtered_needed_inputs = PipeInputSpec()
                    for var_name, concept_code in pipe_needed_inputs.root.items():
                        if var_name != batch_as_input:
                            filtered_needed_inputs.add_requirement(variable_name=var_name, concept_code=concept_code)
                    pipe_needed_inputs = filtered_needed_inputs

                # Add all inputs from this parallel pipe
                for var_name, concept_code in pipe_needed_inputs.root.items():
                    needed_inputs.add_requirement(variable_name=var_name, concept_code=concept_code)

            return needed_inputs
        finally:
            _visited_pipes.discard(self.code)

    @model_validator(mode="after")
    def validate_inputs(self) -> Self:
        # Skip validation during model creation - it will be done in validate_with_libraries()
        return self

    def _validate_inputs(self):
        """
        Validate that the inputs declared for this PipeParallel match what is actually needed.
        """
        static_validation_config = get_config().pipelex.static_validation_config
        default_reaction = static_validation_config.default_reaction
        reactions = static_validation_config.reactions

        the_needed_inputs = self.needed_inputs()

        # Check all required variables are in the inputs
        for required_variable_name, _, _ in the_needed_inputs.detailed_requirements:
            if required_variable_name not in self.inputs.variables:
                missing_input_var_error = StaticValidationError(
                    error_type=StaticValidationErrorType.MISSING_INPUT_VARIABLE,
                    domain_code=self.domain,
                    pipe_code=self.code,
                    variable_names=[required_variable_name],
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
                    domain_code=self.domain,
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
        """
        Perform full validation after all libraries are loaded.
        This is called after all pipes and concepts are available.
        """
        self._validate_inputs()

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

        for sub_pipe in self.parallel_sub_pipes:
            tasks.append(
                sub_pipe.run(
                    calling_pipe_code=self.code,
                    job_metadata=job_metadata,
                    working_memory=working_memory.make_deep_copy(),
                    sub_pipe_run_params=pipe_run_params.make_deep_copy(),
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
            pipeline_run_id=job_metadata.pipeline_run_id,
        )
