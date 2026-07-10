import functools
from typing import TYPE_CHECKING, Any, Literal, cast

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.dry_mock import stamp_mock_main_coordination
from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.hub import get_pipe_router, get_required_pipe
from pipelex.pipe_controllers.pipe_controller import PipeController
from pipelex.pipe_run.exceptions import PipeRunError
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import BatchParams, PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.async_utils import gather_bounded
from pipelex.urls import URLs

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pipelex.core.stuffs.stuff import Stuff
    from pipelex.core.stuffs.stuff_content import StuffContent
    from pipelex.libraries.library_crate import LibraryCrate

# When a single PipeBatch fans out over more than this many items, log a one-time advisory pointing at
# durable execution — bounded fan-out is a basic backpressure effort, not durable, rate-limited execution.
LARGE_BATCH_ADVISORY_THRESHOLD = 100


def resolve_batch_max_concurrency(max_concurrency_setting: int | str) -> int | None:
    """Translate the ``pipeline_execution_config.max_concurrency`` setting into a ``gather_bounded`` bound.

    The config exposes the explicit literal ``"unbounded"``; ``gather_bounded`` takes ``None`` for no
    bound. Any int value is passed through unchanged. Centralizing this guards against passing the
    raw ``"unbounded"`` string into ``gather_bounded``, which would raise ``TypeError`` on its
    ``max_concurrency < 1`` check.
    """
    return None if isinstance(max_concurrency_setting, str) else max_concurrency_setting


class PipeBatch(PipeController):
    type: Literal["PipeBatch"] = "PipeBatch"

    branch_pipe_code: str
    batch_params: BatchParams

    @override
    def required_variables(self) -> set[str]:
        required_variables: set[str] = set()
        # 1. Check that the inputs of the branch_pipe are in the inputs of the pipe
        branch_pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        required_variables.update(branch_pipe.inputs.variables)
        # 2. Check that the input_list_stuff_name is in the inputs of the pipe
        if self.batch_params.input_item_stuff_name not in required_variables:
            msg = f"Input item name '{self.batch_params.input_item_stuff_name}' not found in inputs of branch pipe '{self.branch_pipe_code}'"
            raise ValueError(msg)
        required_variables.remove(self.batch_params.input_item_stuff_name)
        required_variables.add(self.batch_params.input_list_stuff_name)
        return required_variables

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def pipe_dependencies(self) -> set[str]:
        return {self.branch_pipe_code}

    @override
    def validate_inputs_static(self):
        pass

    @override
    def validate_inputs_with_library(self):
        # Check that the item name is in the inputs of the branch_pipe
        branch_pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        if self.batch_params.input_item_stuff_name not in branch_pipe.inputs.variables:
            msg = f"Input item name '{self.batch_params.input_item_stuff_name}' not found in inputs of branch pipe '{self.branch_pipe_code}'"
            raise ValueError(msg)

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        pass

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ) -> None:
        batch_params = pipe_run_params.batch_params or self.batch_params or BatchParams.make_default()
        input_list_stuff_name = batch_params.input_list_stuff_name
        if not self.inputs.is_variable_existing(variable_name=input_list_stuff_name):
            msg = f"Batch input list named '{input_list_stuff_name}' is not in PipeBatch '{self.code}' input requirements: {self.inputs}"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        if not working_memory.is_stuff_exists(input_list_stuff_name):
            msg = f"Input list stuff '{input_list_stuff_name}' required by this PipeBatch '{self.code}' not found in working memory"
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

        input_stuff = working_memory.get_stuff(input_list_stuff_name)
        if not isinstance(input_stuff.content, ListContent):
            msg = (
                f"Input list stuff '{input_list_stuff_name}' of PipeBatch '{self.code}' must be ListContent, "
                f"got {input_stuff.stuff_name or 'unnamed'} = {type(input_stuff.content)}. stuff: {input_stuff}"
            )
            raise PipeRunError(message=msg, run_mode=pipe_run_params.run_mode, pipe_code=self.code)

    @override
    async def _live_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        batch_params = pipe_run_params.batch_params or self.batch_params or BatchParams.make_default()
        input_item_stuff_name = batch_params.input_item_stuff_name
        input_list_stuff_name = batch_params.input_list_stuff_name

        if pipe_run_params.final_stuff_code:
            pipe_run_params.final_stuff_code = None

        pipe_run_params.push_pipe_layer(pipe_code=self.branch_pipe_code)

        input_stuff = working_memory.get_stuff(input_list_stuff_name)
        input_content = cast("ListContent[StuffContent]", input_stuff.content)

        # TODO: Make commented code work when inputing images named "a.b.c"
        sub_pipe = get_required_pipe(pipe_code=self.branch_pipe_code)
        batch_output_stuff_code = StuffFactory.make_stuff_code()

        item_count = len(input_content.items)
        max_concurrency_setting = get_config().pipelex.pipeline_execution_config.max_concurrency
        max_concurrency = resolve_batch_max_concurrency(max_concurrency_setting)
        if item_count > LARGE_BATCH_ADVISORY_THRESHOLD:
            log.warning(
                f"PipeBatch '{self.code}' is fanning out over {item_count} items. Bounded fan-out "
                f"(max_concurrency={max_concurrency_setting}) is a basic backpressure effort, not durable execution — "
                f"for a workload this size, consider a durable execution backend for rate-limited, resumable runs: {URLs.durable_execution}"
            )

        async def _run_branch(item_input_stuff: "Stuff", *, branch_output_item_code: str) -> PipeOutput:
            branch_memory = working_memory.make_deep_copy()
            branch_memory.set_new_main_stuff(stuff=item_input_stuff, name=input_item_stuff_name)

            # We create a deep copy of the run params to avoid modifying the original run params,
            # and we set the final stuff code to use the one provided for the branch pipe.
            # Note: we set output_multiplicity to None to allow inner pipes to use their own
            # multiplicity settings (e.g., a PipeLLM with output="Item[]" should still produce ListContent).
            # PipeBatch aggregates the final outputs of each branch run into a list.
            branch_pipe_run_params = pipe_run_params.model_copy(
                deep=True,
                update={
                    "final_stuff_code": branch_output_item_code,
                    "output_multiplicity": None,
                },
            )
            return await get_pipe_router().run(
                pipe_job=PipeJobFactory.make_pipe_job(
                    pipe=sub_pipe,
                    job_metadata=job_metadata,
                    working_memory=branch_memory,
                    pipe_run_params=branch_pipe_run_params,
                    output_name=None,
                    library_crate=library_crate,
                ),
            )

        # Build one factory per branch. Each factory defers its working-memory deep copy until it
        # actually runs, so gather_bounded materializes at most `max_concurrency` of them at once.
        branch_factories: list[Callable[[], Awaitable[PipeOutput]]] = []
        for branch_index, item in enumerate(input_content.items):
            branch_output_item_code = f"{batch_output_stuff_code}-branch-{branch_index}"
            branch_input_item_code = f"{input_stuff.stuff_code}-branch-{branch_index}"
            item_input_stuff = StuffFactory.make_stuff(
                code=branch_input_item_code,
                concept=self.inputs.get_required_stuff_spec(input_list_stuff_name).concept,
                content=item,
                name=input_item_stuff_name,
            )

            # Register batch item extraction with graph tracer
            if job_metadata.trace_context is not None:
                tracer_manager = GraphTracerManager.get_instance()
                if tracer_manager is not None:
                    # Pass this PipeBatch's node_id so BATCH_ITEM edges can source from the controller
                    batch_controller_node_id = job_metadata.trace_context.parent_node_id
                    tracer_manager.register_batch_item_extraction(
                        lookup_key=job_metadata.trace_context.lookup_key,
                        list_stuff_code=input_stuff.stuff_code,
                        item_stuff_code=branch_input_item_code,
                        item_index=branch_index,
                        batch_controller_node_id=batch_controller_node_id,
                    )

            branch_factories.append(functools.partial(_run_branch, item_input_stuff, branch_output_item_code=branch_output_item_code))

        pipe_outputs = await gather_bounded(branch_factories, max_concurrency=max_concurrency)

        output_items: list[StuffContent] = []
        branch_output_stuff_codes: list[str] = []

        for pipe_output in pipe_outputs:
            branch_output_stuff = pipe_output.main_stuff
            output_items.append(branch_output_stuff.content)
            branch_output_stuff_codes.append(branch_output_stuff.stuff_code)

        list_content: ListContent[StuffContent] = ListContent(items=output_items)
        output_stuff = StuffFactory.make_stuff(
            concept=self.output.concept,
            content=list_content,
            name=output_name,
        )

        # Register batch aggregation with graph tracer
        if job_metadata.trace_context is not None:
            tracer_manager = GraphTracerManager.get_instance()
            if tracer_manager is not None:
                # Pass the PipeBatch's node_id (from trace_context.parent_node_id) so that
                # BATCH_AGGREGATE edges correctly target this PipeBatch node, not a parent
                # controller that may later finish and register as producer of the same output
                batch_controller_node_id = job_metadata.trace_context.parent_node_id
                for agg_index, item_stuff_code in enumerate(branch_output_stuff_codes):
                    tracer_manager.register_batch_aggregation(
                        lookup_key=job_metadata.trace_context.lookup_key,
                        output_list_stuff_code=output_stuff.stuff_code,
                        item_stuff_code=item_stuff_code,
                        item_index=agg_index,
                        batch_controller_node_id=batch_controller_node_id,
                    )

        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "item_count": len(input_content.items),
            "branch_pipe_code": self.branch_pipe_code,
        }
        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)

        return PipeOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_controller_pipe(
        self,
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
        library_crate: "LibraryCrate | None" = None,
    ) -> PipeOutput:
        pipe_output = await self._live_run_controller_pipe(
            job_metadata=job_metadata,
            working_memory=working_memory,
            pipe_run_params=pipe_run_params,
            output_name=output_name,
            library_crate=library_crate,
        )
        # Dry-run coordination: see stamp_mock_main_coordination's docstring (single home, D3).
        main_stuff = pipe_output.main_stuff
        content = main_stuff.content
        if isinstance(content, ListContent):
            list_content = cast("ListContent[StuffContent]", content)
            stamp_mock_main_coordination(list_content.items)
        return pipe_output

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
