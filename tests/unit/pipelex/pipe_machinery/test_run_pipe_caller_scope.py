"""Verify that `PipeAbstract.run_pipe` runs every pipe inside its run's caller scope.

The scope is what attributes a capture made during a run without the run in
hand — an exception, above all, which reaches the interpreter hook only once
the stack has unwound. So these pin both halves: the run's caller is current
while the pipe body runs, and an error escaping the pipe carries that caller.
"""

from typing import Any, Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipe_machinery.pipe_abstract import InputPresenceScan
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.caller_identity import CallerIdentity, find_stamped_caller_identity, get_current_caller_identity
from pipelex.system.job_metadata import JobMetadata, RunMetadata


def _make_pipe(*, mocker: MockerFixture, live_run: Any) -> PipeLLM:
    blueprint = PipeLLMBlueprint(description="Say hello.", output="native.Text", prompt="Say hello.")
    pipe = PipeFactory[PipeLLM].make_from_blueprint(domain_code="caller_domain", pipe_code="say_hello", blueprint=blueprint)
    mocker.patch.object(PipeLLM, "_live_run_operator_pipe", live_run)
    mocker.patch.object(
        PipeLLM,
        "validate_before_run",
        mocker.AsyncMock(return_value=InputPresenceScan(missing_names=[], forced_absent=[], liftable=[])),
    )
    mocker.patch.object(PipeLLM, "validate_after_run", mocker.AsyncMock(return_value=None))
    mocker.patch("pipelex.pipe_machinery.pipe_abstract.GraphTracerManager.get_instance", return_value=None)
    return pipe


def _job_metadata() -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(
            storage_scope="tenant/run-1",
            user_id="caller-7",
            pipeline_run_id="run-1",
            analytics_groups={"organization": "org_caller"},
        ),
    )


_EXPECTED_CALLER = CallerIdentity(user_id="caller-7", analytics_groups={"organization": "org_caller"})


@pytest.mark.asyncio(loop_scope="class")
class TestRunPipeCallerScope:
    async def test_the_runs_caller_is_current_while_the_pipe_runs(self, mocker: MockerFixture, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()
        seen: list[CallerIdentity | None] = []
        main_stuff = Stuff(
            stuff_code="main-code",
            stuff_name="main_stuff",
            concept=Concept(code="Text", domain_code="native", description="Plain text", structure_class_name="TextContent"),
            content=TextContent(text="hello"),
        )
        expected_output = mocker.MagicMock()
        expected_output.working_memory.get_main_stuff.return_value = main_stuff
        expected_output.working_memory.resolve_main_stuff.return_value = main_stuff

        def record_caller(*_args: Any, **_kwargs: Any) -> Any:
            seen.append(get_current_caller_identity())
            return expected_output

        pipe = _make_pipe(mocker=mocker, live_run=mocker.AsyncMock(side_effect=record_caller))

        await pipe.run_pipe(
            job_metadata=_job_metadata(),
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParamsFactory.make_run_params(),
        )

        assert seen == [_EXPECTED_CALLER]
        assert get_current_caller_identity() is None

    async def test_an_error_escaping_the_pipe_carries_the_runs_caller(self, mocker: MockerFixture, load_empty_library: Callable[[], str]) -> None:
        load_empty_library()

        pipe = _make_pipe(mocker=mocker, live_run=mocker.AsyncMock(side_effect=RuntimeError("the pipe body failed")))

        with pytest.raises(RuntimeError, match="the pipe body failed") as exc_info:
            await pipe.run_pipe(
                job_metadata=_job_metadata(),
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        assert find_stamped_caller_identity(exception=exc_info.value) == _EXPECTED_CALLER
        assert get_current_caller_identity() is None
