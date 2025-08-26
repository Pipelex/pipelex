import asyncio
from typing import Any, Coroutine, List, Optional, Set, cast

import shortuuid
from pydantic import model_validator
from typing_extensions import Self, override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, WorkingMemory
from pipelex.core.pipes.pipe_input_spec import PipeInputSpec
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.pipes.pipe_run_params import BatchParams, PipeRunMode, PipeRunParams
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import ListContent, StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.exceptions import (
    PipeInputError,
    PipeInputNotFoundError,
    WorkingMemoryStuffNotFoundError,
)
from pipelex.hub import get_pipeline_tracker, get_required_pipe
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipeline.job_metadata import JobMetadata


class PipeBatch(PipeController):
    """Runs a PipeSequence in parallel for each item in a list."""

    branch_pipe_code: str
    batch_params: Optional[BatchParams] = None

    @override
    def pipe_dependencies(self) -> Set[str]:
        return set([self.branch_pipe_code])

    @override
    def validate_output(self):
        pass

    @model_validator(mode="after")
    def validate_required_variables(self) -> Self:
        # Skip for now
        return self

    @override
    def validate_with_libraries(self):
        self._validate_required_variables()

    def _validate_required_variables(self) -> Self:
        # Now check that the required vairables ARE in the inputs of the pipe
        required_variables = self.required_variables()
        for variable_name in required_variables:
            if variable_name not in self.inputs.root.keys():
                raise PipeInputError(f"Input '{variable_name}' of pipe '{self.code}' is not in the inputs of the pipe '{self.branch_pipe_code}'")
        return self

    @override
    def required_variables(self) -> Set[str]:
        required_variables: Set[str] = set()
        # 1. Check that the inputs of the pipe branch_pipe_code are in the inputs of the pipe
        pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        for variable_name, _ in pipe.inputs.items:
            required_variables.add(variable_name)
        # 2. Check that the input_item_stuff_name is in the inputs of the pipe
        if self.batch_params and self.batch_params.input_item_stuff_name:
            required_variables.add(self.batch_params.input_item_stuff_name)
        return required_variables

    @override
    def needed_inputs(self) -> PipeInputSpec:
        return self.inputs

    async def _run_batch_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """Common logic for running or dry-running a pipe in batch mode."""
        batch_params = pipe_run_params.batch_params or self.batch_params or BatchParams.make_default()
        input_item_stuff_name = batch_params.input_item_stuff_name
        try:
            input_item_concept_code = self.inputs.get_required_input_requirement(input_item_stuff_name)
        except PipeInputNotFoundError as exc:
            raise PipeInputError(
                f"Batch input item stuff named '{input_item_stuff_name}' is not in this PipeBatch '{self.code}' input spec: {self.inputs}"
            ) from exc

        if pipe_run_params.final_stuff_code:
            method_name = "dry_run_pipe" if pipe_run_params.run_mode == PipeRunMode.DRY else "_run_controller_pipe"
            log.debug(f"PipeBatch.{method_name}() final_stuff_code: {pipe_run_params.final_stuff_code}")
            pipe_run_params.final_stuff_code = None

        pipe_run_params.push_pipe_layer(pipe_code=self.branch_pipe_code)
        try:
            input_stuff = working_memory.get_stuff(batch_params.input_list_stuff_name)
        except WorkingMemoryStuffNotFoundError as exc:
            raise PipeInputError(
                f"Input list stuff '{batch_params.input_list_stuff_name}' required by this PipeBatch '{self.code}' not found in working memory: {exc}"
            ) from exc
        input_stuff_code = input_stuff.stuff_code
        input_content = input_stuff.content

        if not isinstance(input_content, ListContent):
            raise PipeInputError(
                f"Input of PipeBatch must be ListContent, got {input_stuff.stuff_name or 'unnamed'} = {type(input_content)}. stuff: {input_stuff}"
            )
        input_content = cast(ListContent[StuffContent], input_content)

        # TODO: Make commented code work when inputing images named "a.b.c"
        sub_pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        nb_history_items_limit = get_config().pipelex.tracker_config.applied_nb_items_limit
        batch_output_stuff_code = shortuuid.uuid()
        tasks: List[Coroutine[Any, Any, PipeOutput]] = []
        item_stuffs: List[Stuff] = []
        required_stuff_lists: List[List[Stuff]] = []
        branch_output_item_codes: List[str] = []

        for branch_index, item in enumerate(input_content.items):
            branch_output_item_code = f"{batch_output_stuff_code}-branch-{branch_index}"
            branch_output_item_codes.append(branch_output_item_code)
            if nb_history_items_limit and branch_index >= nb_history_items_limit:
                break
            branch_input_item_code = f"{input_stuff_code}-branch-{branch_index}"
            item_input_stuff = StuffFactory.make_stuff(
                code=branch_input_item_code,
                concept=input_item_concept_code.concept,
                content=item,
                name=input_item_stuff_name,
            )
            item_stuffs.append(item_input_stuff)
            branch_memory = working_memory.make_deep_copy()
            branch_memory.set_new_main_stuff(stuff=item_input_stuff, name=input_item_stuff_name)

            required_variables = sub_pipe.required_variables()
            required_stuffs = branch_memory.get_existing_stuffs(names=required_variables)
            required_stuffs = [required_stuff for required_stuff in required_stuffs if required_stuff.stuff_code != input_stuff_code]
            required_stuff_lists.append(required_stuffs)
            branch_pipe_run_params = pipe_run_params.deep_copy_with_final_stuff_code(final_stuff_code=branch_output_item_code)

            if pipe_run_params.run_mode == PipeRunMode.DRY:
                branch_pipe_run_params.run_mode = PipeRunMode.DRY
                task = sub_pipe.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=branch_memory,
                    output_name=f"Batch result {branch_index + 1} of {output_name}",
                    pipe_run_params=branch_pipe_run_params,
                )
            else:
                task = sub_pipe.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=branch_memory,
                    output_name=f"Batch result {branch_index + 1} of {output_name}",
                    pipe_run_params=branch_pipe_run_params,
                )
            tasks.append(task)

        pipe_outputs = await asyncio.gather(*tasks)

        output_items: List[StuffContent] = []
        output_stuffs: List[Stuff] = []
        output_stuff_code = shortuuid.uuid()[:5]
        for branch_index, pipe_output in enumerate(pipe_outputs):
            branch_output_stuff = pipe_output.main_stuff
            output_stuffs.append(branch_output_stuff)
            output_items.append(branch_output_stuff.content)

        list_content: ListContent[StuffContent] = ListContent(items=output_items)
        output_stuff = StuffFactory.make_stuff(
            code=output_stuff_code,
            concept=self.output,
            content=list_content,
            name=output_name,
        )

        method_name = "dry_run_pipe" if pipe_run_params.run_mode == PipeRunMode.DRY else "run_pipe"
        for branch_index, (
            required_stuff_list,
            item_input_stuff,
            item_output_stuff,
        ) in enumerate(zip(required_stuff_lists, item_stuffs, output_stuffs)):
            get_pipeline_tracker().add_batch_step(
                from_stuff=input_stuff,
                to_stuff=item_input_stuff,
                to_branch_index=branch_index,
                pipe_layer=pipe_run_params.pipe_layers,
                comment=f"PipeBatch.{method_name}() in zip",
            )
            for required_stuff in required_stuff_list:
                get_pipeline_tracker().add_pipe_step(
                    from_stuff=required_stuff,
                    to_stuff=item_output_stuff,
                    pipe_code=self.branch_pipe_code,
                    pipe_layer=pipe_run_params.pipe_layers,
                    comment=f"PipeBatch.{method_name}() on required_stuff_list",
                    as_item_index=branch_index,
                    is_with_edge=(required_stuff.stuff_name != MAIN_STUFF_NAME),
                )

        for branch_index, branch_output_stuff in enumerate(output_stuffs):
            branch_output_item_code = branch_output_item_codes[branch_index]
            get_pipeline_tracker().add_aggregate_step(
                from_stuff=branch_output_stuff,
                to_stuff=output_stuff,
                pipe_layer=pipe_run_params.pipe_layers,
                comment=f"PipeBatch.{method_name}() on branch_index of batch",
            )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """Run a pipe in batch mode for each item in the input list."""
        return await self._run_batch_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )

    @override
    async def _dry_run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """Dry run a pipe in batch mode for each item in the input list."""
        return await self._run_batch_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
        )
