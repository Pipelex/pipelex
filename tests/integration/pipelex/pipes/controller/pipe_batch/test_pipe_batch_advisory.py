"""PipeBatch hands its router the advice on a live batch's width, so only a router that is not durable advises durability.

The hook is `PipeRouterProtocol.advise_on_batch`: an in-process router logs the large-batch advisory past its threshold,
and a durable router, which already runs the batch durably, overrides it and does not tell the run to use durable
execution. These tests pin when the hook is called, with what, and that an override silences the advisory.
"""

from collections.abc import Callable
from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex import log
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_pipe_library, scoped_pipe_router
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.large_batch_advisory import LARGE_BATCH_ADVISORY_THRESHOLD
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import pipe_func

_DOMAIN_CODE = "test_batch_advisory"
_BATCH_CODE = "advisory_batch"
_BRANCH_CODE = "advisory_shout"
_ADVISORY_MESSAGE = "A PipeBatch fans out over a large list without durable execution"


@pipe_func()
def batch_advisory_shout_item(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=working_memory.get_stuff_as_str(name="item").upper())


class _DurableRouter(PipeRouter):
    """A router standing in for a durable one: it runs every batch durably, so it gives no advice on its width."""

    @override
    def advise_on_batch(self, *, pipe_code: str, item_count: int, max_concurrency: int | None) -> None:
        del pipe_code, item_count, max_concurrency


def _build_batch() -> PipeBatch:
    """A batch over Text items whose branch uppercases each item."""
    shout_pipe = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code=_BRANCH_CODE,
        blueprint=PipeFuncBlueprint(
            description="Uppercase the batch item",
            inputs={"item": "Text"},
            output="Text",
            function_name=f"{__name__}.batch_advisory_shout_item",
        ),
    )
    pipe_library = get_pipe_library()
    pipe_library.add_new_pipe(pipe=shout_pipe)

    batch = PipeFactory[PipeBatch].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code=_BATCH_CODE,
        blueprint=PipeBatchBlueprint(
            description="Batch the shout over the items",
            # Domain-qualified: this blueprint is hand-built, so it never goes through the crate qualification pass.
            branch_pipe_code=f"{_DOMAIN_CODE}.{_BRANCH_CODE}",
            output="Text",
            input_list_name="items",
            input_item_name="item",
            inputs={"items": "Text"},
        ),
    )
    pipe_library.add_new_pipe(pipe=batch)
    return batch


def _make_batch_job(*, batch: PipeBatch, job_metadata: JobMetadata, item_count: int, run_mode: PipeRunMode) -> PipeJob:
    items_stuff = StuffFactory.make_stuff(
        concept=batch.inputs.get_required_stuff_spec("items").concept,
        content=ListContent[TextContent](items=[TextContent(text=f"item {index}") for index in range(item_count)]),
        name="items",
    )
    return PipeJobFactory.make_pipe_job(
        pipe=batch,
        job_metadata=job_metadata,
        working_memory=WorkingMemoryFactory.make_from_single_stuff(items_stuff),
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=run_mode),
    )


def _advisory_calls(warning_spy: MagicMock) -> int:
    return sum(1 for call in warning_spy.call_args_list if call.args and call.args[0] == _ADVISORY_MESSAGE)


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchAdvisory:
    async def test_the_router_is_asked_once_with_the_width_and_the_bound(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """One call per live batch, naming the batch, its width and the run's frozen bound."""
        load_empty_library()
        batch = _build_batch()
        router = PipeRouter()
        advise_spy = mocker.spy(router, "advise_on_batch")
        job = _make_batch_job(batch=batch, job_metadata=job_metadata, item_count=3, run_mode=PipeRunMode.LIVE)

        with scoped_pipe_router(router):
            await router.run(job)

        advise_spy.assert_called_once_with(pipe_code=_BATCH_CODE, item_count=3, max_concurrency=job.pipe_run_params.batch_max_concurrency)

    async def test_an_in_process_router_advises_durable_execution_for_a_large_batch(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        load_empty_library()
        batch = _build_batch()
        router = PipeRouter()
        warning_spy = mocker.patch.object(log, "warning")

        with scoped_pipe_router(router):
            await router.run(
                _make_batch_job(batch=batch, job_metadata=job_metadata, item_count=LARGE_BATCH_ADVISORY_THRESHOLD + 1, run_mode=PipeRunMode.LIVE)
            )

        assert _advisory_calls(warning_spy) == 1

    async def test_a_durable_router_is_not_told_to_use_durable_execution(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """The advisory fired on a run already on Temporal: a router that overrides the hook silences it."""
        load_empty_library()
        batch = _build_batch()
        router = _DurableRouter()
        warning_spy = mocker.patch.object(log, "warning")

        with scoped_pipe_router(router):
            await router.run(
                _make_batch_job(batch=batch, job_metadata=job_metadata, item_count=LARGE_BATCH_ADVISORY_THRESHOLD + 1, run_mode=PipeRunMode.LIVE)
            )

        assert _advisory_calls(warning_spy) == 0

    async def test_a_dry_run_is_advised_nothing(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """A dry run goes through the same method as a live one, yet the router is not asked for its advice."""
        load_empty_library()
        batch = _build_batch()
        router = PipeRouter()
        advise_spy = mocker.spy(router, "advise_on_batch")
        warning_spy = mocker.patch.object(log, "warning")

        with scoped_pipe_router(router):
            await router.run(
                _make_batch_job(batch=batch, job_metadata=job_metadata, item_count=LARGE_BATCH_ADVISORY_THRESHOLD + 1, run_mode=PipeRunMode.DRY)
            )

        advise_spy.assert_not_called()
        assert _advisory_calls(warning_spy) == 0
