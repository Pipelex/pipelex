"""PipeBatch's branch dispatch: it goes through the `run_batch_branch` hook, and its fan-out bound
comes off the payload rather than live config.

Both are the core half of the flat-topology seam. The hook is the ONLY signal a distributed router
gets that a dispatch is a per-item fan-out branch (the branch job is otherwise indistinguishable
from a sequence step); the frozen bound is what keeps the fan-out grouping a pure function of the
run, so a config redeploy cannot reshape an in-flight batch.
"""

from collections.abc import Awaitable, Callable, Sequence

import pytest
from typing_extensions import override

from pipelex.config import get_config
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library, scoped_pipe_router
from pipelex.pipe_controllers.batch import pipe_batch as pipe_batch_module
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import func_registry

_DOMAIN_CODE = "test_batch_branch_dispatch"


def batch_branch_dispatch_shout_item(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=working_memory.get_stuff_as_str(name="item").upper())


class _HookCountingRouter(PipeRouter):
    """Real in-process router that records which dispatch door each job came through."""

    def __init__(self) -> None:
        super().__init__()
        self.branch_dispatched_pipe_codes: list[str] = []
        self.plain_run_pipe_codes: list[str] = []

    @override
    async def run(self, pipe_job: PipeJob) -> PipeOutput:
        self.plain_run_pipe_codes.append(pipe_job.pipe.code)
        return await super().run(pipe_job)

    @override
    async def run_batch_branch(self, pipe_job: PipeJob) -> PipeOutput:
        self.branch_dispatched_pipe_codes.append(pipe_job.pipe.code)
        return await super().run_batch_branch(pipe_job)


def _build_batch() -> PipeBatch:
    """A batch over Text items whose branch just uppercases each item."""
    shout_pipe = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="branch_dispatch_shout",
        blueprint=PipeFuncBlueprint(
            description="Uppercase the batch item",
            inputs={"item": "Text"},
            output="Text",
            function_name="batch_branch_dispatch_shout_item",
        ),
    )
    pipe_library = get_pipe_library()
    pipe_library.add_new_pipe(pipe=shout_pipe)

    batch = PipeFactory[PipeBatch].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code="branch_dispatch_batch",
        blueprint=PipeBatchBlueprint(
            description="Batch the shout over the items",
            branch_pipe_code="branch_dispatch_shout",
            output="Text",
            input_list_name="items",
            input_item_name="item",
            inputs={"items": "Text"},
        ),
    )
    pipe_library.add_new_pipe(pipe=batch)
    return batch


def _make_items_memory(batch: PipeBatch, texts: list[str]):
    items_stuff = StuffFactory.make_stuff(
        concept=batch.inputs.get_required_stuff_spec("items").concept,
        content=ListContent[TextContent](items=[TextContent(text=text) for text in texts]),
        name="items",
    )
    return WorkingMemoryFactory.make_from_single_stuff(items_stuff)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchBranchDispatch:
    @classmethod
    def setup_class(cls):
        func_registry.register_function(batch_branch_dispatch_shout_item)

    @classmethod
    def teardown_class(cls):
        if func_registry.has_function(batch_branch_dispatch_shout_item.__name__):
            func_registry.unregister_function_by_name(batch_branch_dispatch_shout_item.__name__)

    async def test_branches_dispatch_through_the_hook(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str]):
        """One `run_batch_branch` call per item, and the batch itself never enters through the hook."""
        load_empty_library()
        batch = _build_batch()
        router = _HookCountingRouter()

        with scoped_pipe_router(router):
            await batch.run_pipe(
                job_metadata=job_metadata,
                working_memory=_make_items_memory(batch, ["alpha", "beta", "gamma"]),
                pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
            )

        assert router.branch_dispatched_pipe_codes == ["branch_dispatch_shout"] * 3
        assert "branch_dispatch_batch" not in router.branch_dispatched_pipe_codes

    async def test_fan_out_bound_comes_off_the_payload_not_live_config(
        self,
        job_metadata: JobMetadata,
        load_empty_library: Callable[[], str],
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Params built under `max_concurrency = 2` keep that bound after the config flips to 5.

        This is the replay hazard the freeze exists for: the bound is `gather_bounded`'s chunk size,
        so a live read here would let a mid-run worker redeploy regroup the branch dispatches.
        """
        load_empty_library()
        batch = _build_batch()

        captured_bounds: list[int | None] = []
        real_gather_bounded = pipe_batch_module.gather_bounded

        async def _spying_gather_bounded(
            task_factories: "Sequence[Callable[[], Awaitable[PipeOutput]]]",
            *,
            max_concurrency: int | None,
        ) -> list[PipeOutput]:
            captured_bounds.append(max_concurrency)
            return await real_gather_bounded(task_factories, max_concurrency=max_concurrency)

        monkeypatch.setattr(pipe_batch_module, "gather_bounded", _spying_gather_bounded)

        execution_config = get_config().pipelex.pipeline_execution_config
        original_setting = execution_config.max_concurrency
        try:
            execution_config.max_concurrency = 2
            run_params = PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE)
            execution_config.max_concurrency = 5

            with scoped_pipe_router(_HookCountingRouter()):
                await batch.run_pipe(
                    job_metadata=job_metadata,
                    working_memory=_make_items_memory(batch, ["alpha", "beta", "gamma"]),
                    pipe_run_params=run_params,
                )
        finally:
            execution_config.max_concurrency = original_setting

        assert captured_bounds == [2]
