import asyncio
from typing import TYPE_CHECKING, Any, Literal

from pydantic import field_validator, model_validator
from typing_extensions import override

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.pipes.inputs.exceptions import InputStuffSpecNotFoundError
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.inputs.input_stuff_specs_factory import InputStuffSpecsFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_required_pipe
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_run_params import PipeRunParams
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

    @field_validator("parallel_sub_pipes", mode="before")
    @classmethod
    def validate_parallel_sub_pipes(cls, parallel_sub_pipes: list[SubPipe]) -> list[SubPipe]:
        seen_output_names: set[str] = set()
        for sub_pipe in parallel_sub_pipes:
            if not sub_pipe.output_name:
                msg = f"PipeParallel '{cls.code}' sub-pipe '{sub_pipe.pipe_code}' output name not specified"
                raise ValueError(msg)
            if sub_pipe.output_name in seen_output_names:
                msg = (
                    f"PipeParallel '{cls.code}' sub-pipe '{sub_pipe.pipe_code}' output name '{sub_pipe.output_name}' "
                    "is already used by another sub-pipe"
                )
                raise ValueError(msg)
            seen_output_names.add(sub_pipe.output_name)
        return parallel_sub_pipes

    @override
    def required_variables(self) -> set[str]:
        return set()

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

        for sub_pipe in self.parallel_sub_pipes:
            pipe = get_required_pipe(pipe_code=sub_pipe.pipe_code)
            # Use the centralized recursion detection
            pipe_needed_inputs = pipe.needed_inputs(visited_pipes_with_current)
            if sub_pipe.batch_params:
                try:
                    stuff_spec = pipe_needed_inputs.get_required_stuff_spec(variable_name=sub_pipe.batch_params.input_item_stuff_name)
                except InputStuffSpecNotFoundError as exc:
                    msg = (
                        f"Batch input item named '{sub_pipe.batch_params.input_item_stuff_name}' is not "
                        f"in this Parallel Pipe '{self.code}' input requirements: {pipe_needed_inputs}"
                    )
                    raise PipeValidationError(message=msg) from exc
                needed_inputs.add_stuff_spec(
                    variable_name=sub_pipe.batch_params.input_list_stuff_name,
                    concept=stuff_spec.concept,
                    multiplicity=True,
                )
                for input_name, stuff_spec in pipe_needed_inputs.items:
                    if input_name != sub_pipe.batch_params.input_item_stuff_name:
                        needed_inputs.add_stuff_spec(input_name, stuff_spec.concept, stuff_spec.multiplicity)
            else:
                for input_name, stuff_spec in pipe_needed_inputs.items:
                    needed_inputs.add_stuff_spec(input_name, stuff_spec.concept, stuff_spec.multiplicity)
        return needed_inputs

    @model_validator(mode="after")
    def validate_fields_add_each_output_and_combined_output(self) -> Self:
        # Validate that either add_each_output or combined_output is set
        if not self.add_each_output and not self.combined_output:
            msg = f"PipeParallel'{self.code}'requires either add_each_output or combined_output to be set"
            raise ValueError(msg)

        return self

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
        pass

    @override
    def pipe_dependencies(self) -> set[str]:
        return {sub_pipe.pipe_code for sub_pipe in self.parallel_sub_pipes}

    @override
    async def _live_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        if pipe_run_params.final_stuff_code:
            log.verbose(f"PipeBatch.run_pipe() final_stuff_code: {pipe_run_params.final_stuff_code}")
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
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)
            output_stuff_content_items.append(output_stuff.content)
            if sub_pipe_output_name in output_stuffs:
                # TODO: check that at the blueprint / factory level
                msg = f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            output_stuffs[sub_pipe_output_name] = output_stuff
            if sub_pipe_output_name in output_stuff_contents:
                # TODO: check that at the blueprint / factory level
                msg = f"PipeParallel requires unique output names for each parallel sub pipe, but {sub_pipe_output_name} is already used"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content
            log.verbose(f"PipeParallel '{self.code}': output_stuff_contents[{sub_pipe_output_name}]: {output_stuff_contents[sub_pipe_output_name]}")

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

    @override
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeOutput:
        # 1. Validate that all sub-pipes exist
        for sub_pipe in self.parallel_sub_pipes:
            try:
                get_required_pipe(pipe_code=sub_pipe.pipe_code)
            except PipeNotFoundError as exc:
                msg = f"Dry run failed for pipe '{self.code}' (PipeParallel): sub-pipe '{sub_pipe.pipe_code}' not found"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code) from exc

        # 2. Run all sub-pipes in dry mode
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

        # 3. Process outputs as in the regular run
        output_stuffs: dict[str, Stuff] = {}
        output_stuff_contents: dict[str, StuffContent] = {}

        for output_index, pipe_output in enumerate(pipe_outputs):
            output_stuff = pipe_output.main_stuff
            sub_pipe_output_name = self.parallel_sub_pipes[output_index].output_name
            if not sub_pipe_output_name:
                sub_pipe_code = self.parallel_sub_pipes[output_index].pipe_code
                msg = f"Dry run failed for pipe '{self.code}' (PipeParallel): sub-pipe '{sub_pipe_code}' output name not specified"
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

            if self.add_each_output:
                working_memory.add_new_stuff(name=sub_pipe_output_name, stuff=output_stuff)

            if sub_pipe_output_name in output_stuffs:
                sub_pipe_code = self.parallel_sub_pipes[output_index].pipe_code
                msg = (
                    f"Dry run failed for pipe '{self.code}' (PipeParallel): sub-pipe '{sub_pipe_code}' duplicate output name '{sub_pipe_output_name}'"
                )
                raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

            output_stuffs[sub_pipe_output_name] = output_stuff
            output_stuff_contents[sub_pipe_output_name] = output_stuff.content

        # 4. Handle combined output if specified
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
