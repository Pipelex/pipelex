import asyncio
from typing import Any, Coroutine, List, Optional, Set, cast

import shortuuid
from typing_extensions import override

from pipelex import log
from pipelex.config import get_config
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import BatchParams, PipeRunParams
from pipelex.core.stuff import Stuff
from pipelex.core.stuff_content import ListContent, StuffContent
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import PipeExecutionError
from pipelex.hub import get_pipe_router
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
    async def _run_controller_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: Optional[str] = None,
    ) -> PipeOutput:
        """Run a sequence of steps in batch for each item in the input list."""
        if not self.input_concept_code:
            raise PipeExecutionError(f"Missing input concept code for pipe '{self.code}' but it is required for PipeBatch")
        if pipe_run_params.final_stuff_code:
            log.debug(f"PipeBatch.run_pipe() final_stuff_code: {pipe_run_params.final_stuff_code}")
            pipe_run_params.final_stuff_code = None

        pipe_run_params.push_pipe_layer(pipe_code=self.branch_pipe_code)
        batch_params = pipe_run_params.batch_params or self.batch_params or BatchParams.make_default()
        input_stuff_key = batch_params.input_list_stuff_name
        input_stuff = working_memory.get_stuff(input_stuff_key)
        input_stuff_code = input_stuff.stuff_code
        input_content = input_stuff.content

        if not isinstance(input_content, ListContent):
            raise ValueError(
                f"Input of PipeBatch must be ListContent, got {input_stuff.stuff_name or 'unnamed'} = {type(input_content)}. stuff: {input_stuff}"
            )

        # TODO: Make commented code work when inputing images named "a.b.c"
        # sub_pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        nb_history_items_limit = get_config().pipelex.tracker_config.applied_nb_items_limit
        pipe_router = get_pipe_router()
        input_content = cast(ListContent[StuffContent], input_content)
        batch_output_stuff_code = shortuuid.uuid()
        tasks: List[Coroutine[Any, Any, PipeOutput]] = []
        item_stuffs: List[Stuff] = []
        # required_stuff_lists: List[List[Stuff]] = []
        branch_output_item_codes: List[str] = []
        for branch_index, item in enumerate(input_content.items):
            branch_output_item_code = f"{batch_output_stuff_code}-branch-{branch_index}"
            branch_output_item_codes.append(branch_output_item_code)
            if nb_history_items_limit and branch_index >= nb_history_items_limit:
                break
            branch_input_item_code = f"{input_stuff_code}-branch-{branch_index}"
            item_input_stuff = StuffFactory.make_stuff(
                code=branch_input_item_code,
                concept_code=self.input_concept_code,
                content=item,
                name=batch_params.input_item_stuff_name,
            )
            item_stuffs.append(item_input_stuff)
            branch_memory = working_memory.make_deep_copy()
            branch_memory.set_new_main_stuff(stuff=item_input_stuff, name=batch_params.input_item_stuff_name)

            # required_variables = sub_pipe.required_variables()
            # required_stuffs = branch_memory.get_stuffs(names=required_variables)
            # required_stuffs = [required_stuff for required_stuff in required_stuffs if required_stuff.stuff_code != input_stuff_code]
            # required_stuff_lists.append(required_stuffs)
            branch_pipe_run_params = pipe_run_params.model_copy(
                deep=True,
                update={
                    "final_stuff_code": branch_output_item_code,
                },
            )
            tasks.append(
                pipe_router.run_pipe_code(
                    pipe_code=self.branch_pipe_code,
                    job_metadata=job_metadata,
                    working_memory=branch_memory,
                    output_name=f"Batch result {branch_index + 1} of {output_name}",
                    pipe_run_params=branch_pipe_run_params,
                )
            )

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
            concept_code=self.output_concept_code,
            content=list_content,
            name=output_name,
        )

        # for branch_index, (required_stuff_list, item_input_stuff, item_output_stuff) in enumerate(
        #     zip(required_stuff_lists, item_stuffs, output_stuffs)
        # ):
        #     get_pipeline_tracker().add_batch_step(
        #         from_stuff=input_stuff,
        #         to_stuff=item_input_stuff,
        #         to_branch_index=branch_index,
        #         pipe_layer=pipe_run_params.pipe_layers,
        #         comment="PipeBatch.run_pipe() in zip",
        #     )
        #     for required_stuff in required_stuff_list:
        #         get_pipeline_tracker().add_pipe_step(
        #             from_stuff=required_stuff,
        #             to_stuff=item_output_stuff,
        #             pipe_code=self.branch_pipe_code,
        #             pipe_layer=pipe_run_params.pipe_layers,
        #             comment="PipeBatch.run_pipe() on required_stuff_list",
        #             as_item_index=branch_index,
        #             is_with_edge=(required_stuff.stuff_name != MAIN_STUFF_NAME),
        #         )

        # for branch_index, branch_output_stuff in enumerate(output_stuffs):
        #     branch_output_item_code = branch_output_item_codes[branch_index]
        #     get_pipeline_tracker().add_aggregate_step(
        #         from_stuff=branch_output_stuff,
        #         to_stuff=output_stuff,
        #         pipe_layer=pipe_run_params.pipe_layers,
        #         comment="PipeBatch.run_pipe() on branch_index of batch",
        #     )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        return PipeOutput(
            working_memory=working_memory,
        )
