"""PipeBatch asks its router once, before any branch starts, whether the batch fits.

The question is `PipeRouterProtocol.check_batch_fits`: in-process routers answer yes without looking, and a durable
router may refuse a batch whose branches would pass what its run's history can hold, by raising
`PipeBatchTooWideError`. These tests pin when the question is asked, with what, and what a refusal leaves behind.
"""

from collections.abc import Callable
from typing import cast

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.problem import ProblemView
from pipelex.interpreter_hub import get_pipe_library, scoped_pipe_router
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.exceptions import PipeBatchTooWideError
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.system.registries.func_registry import pipe_func

_DOMAIN_CODE = "test_batch_fits_check"
_BATCH_CODE = "fits_check_batch"
_BRANCH_CODE = "fits_check_shout"


@pipe_func()
def batch_fits_check_shout_item(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text=working_memory.get_stuff_as_str(name="item").upper())


class _RecordingRouter(PipeRouter):
    """Real in-process router that keeps every branch job it dispatches."""

    def __init__(self) -> None:
        super().__init__()
        self.branch_jobs: list[PipeJob] = []

    @override
    async def run_batch_branch(self, pipe_job: PipeJob) -> PipeOutput:
        self.branch_jobs.append(pipe_job)
        return await super().run_batch_branch(pipe_job)


class _RefusingRouter(_RecordingRouter):
    """A router standing in for a durable one whose run's history has no room for the batch."""

    @override
    def check_batch_fits(self, *, pipe_code: str, input_list_label: str, item_count: int, first_branch_job: PipeJob) -> None:
        raise PipeBatchTooWideError(
            pipe_code=pipe_code,
            input_list_label=input_list_label,
            item_count=item_count,
            estimated_bytes=item_count * 28_000,
            estimated_events=item_count * 6,
            bytes_left=50_000,
            events_left=1_000,
            max_fitting_item_count=1,
        )


def _build_batch() -> PipeBatch:
    """A batch over Text items whose branch uppercases each item."""
    shout_pipe = PipeFactory[PipeFunc].make_from_blueprint(
        domain_code=_DOMAIN_CODE,
        pipe_code=_BRANCH_CODE,
        blueprint=PipeFuncBlueprint(
            description="Uppercase the batch item",
            inputs={"item": "Text"},
            output="Text",
            function_name=f"{__name__}.batch_fits_check_shout_item",
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


def _make_items_memory(*, batch: PipeBatch, texts: list[str]) -> WorkingMemory:
    items_stuff = StuffFactory.make_stuff(
        concept=batch.inputs.get_required_stuff_spec("items").concept,
        content=ListContent[TextContent](items=[TextContent(text=text) for text in texts]),
        name="items",
    )
    return WorkingMemoryFactory.make_from_single_stuff(items_stuff)


def _make_batch_job(*, batch: PipeBatch, job_metadata: JobMetadata, texts: list[str]) -> PipeJob:
    return PipeJobFactory.make_pipe_job(
        pipe=batch,
        job_metadata=job_metadata,
        working_memory=_make_items_memory(batch=batch, texts=texts),
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeBatchFitsCheck:
    async def test_the_router_is_asked_once_with_the_first_branch_job(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """One question per batch, naming the batch, its list and its width, with the job branch 1 then dispatches."""
        load_empty_library()
        batch = _build_batch()
        router = _RecordingRouter()
        check_spy = mocker.spy(router, "check_batch_fits")

        with scoped_pipe_router(router):
            await router.run(_make_batch_job(batch=batch, job_metadata=job_metadata, texts=["alpha", "beta", "gamma"]))

        check_spy.assert_called_once()
        call_kwargs = check_spy.call_args.kwargs
        assert call_kwargs["pipe_code"] == _BATCH_CODE
        assert call_kwargs["input_list_label"] == "items"
        assert call_kwargs["item_count"] == 3
        # Each branch's memory gains its output as it runs, so the item a job was built for is read under its own name.
        first_item_jobs = [job for job in router.branch_jobs if job.get_working_memory().get_stuff("item").stuff_code.endswith("-branch-0")]
        assert len(first_item_jobs) == 1
        first_branch_job = call_kwargs["first_branch_job"]
        assert first_branch_job is first_item_jobs[0]
        assert first_branch_job.pipe.code == _BRANCH_CODE
        assert first_branch_job.get_working_memory().get_stuff_as_str(name="item") == "alpha"
        assert len(router.branch_jobs) == 3

    async def test_an_empty_list_asks_nothing(self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        """A batch over no item starts nothing, so the router is not asked."""
        load_empty_library()
        batch = _build_batch()
        router = _RecordingRouter()
        check_spy = mocker.spy(router, "check_batch_fits")

        with scoped_pipe_router(router):
            output = await router.run(_make_batch_job(batch=batch, job_metadata=job_metadata, texts=[]))

        check_spy.assert_not_called()
        assert router.branch_jobs == []
        output_content = output.working_memory.get_main_stuff().content
        assert isinstance(output_content, ListContent)
        assert cast("ListContent[TextContent]", output_content).items == []

    async def test_a_refusal_stops_the_batch_before_its_fan_out_and_is_located_at_it(
        self, job_metadata: JobMetadata, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """A refused batch records no fan-out, starts no branch, and fails located at the PipeBatch as input.too_large."""
        load_empty_library()
        batch = _build_batch()
        router = _RefusingRouter()
        fan_out_spy = mocker.spy(PipeBatch, "_register_fan_out")

        with scoped_pipe_router(router), pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_batch_job(batch=batch, job_metadata=job_metadata, texts=["alpha", "beta", "gamma"]))

        assert router.branch_jobs == []
        fan_out_spy.assert_not_called()
        location = find_failure_location(error=exc_info.value)
        assert location is not None
        assert location.pipe_code == _BATCH_CODE
        assert isinstance(exc_info.value.__cause__, PipeBatchTooWideError)

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_TOO_LARGE
        assert caller.location is not None
        assert caller.location.pipe == _BATCH_CODE
        assert caller.location.input == "items"
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "items", "limit": 1, "size": 3}
