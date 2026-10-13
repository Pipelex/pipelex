"""Verify that tracing a pipe's failure never changes the error the run fails with."""

from typing import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.pipe_machinery.pipe_abstract import InputPresenceScan
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from tests.unit.pipelex.graph.conftest import make_trace_context


@pytest.mark.asyncio(loop_scope="class")
class TestRunPipeTracedFailure:
    async def test_a_failure_whose_report_cannot_be_built_fails_the_run_with_the_pipes_own_error(
        self,
        mocker: MockerFixture,
        load_empty_library: Callable[[], str],
    ) -> None:
        """Building the failure's report runs while the pipe's error is on its way out: when it raises, the node records
        the error's text, and the run still fails with the pipe's own error, never with the report's.
        """
        load_empty_library()
        pipe = PipeFactory[PipeLLM].make_from_blueprint(
            domain_code="greeting_domain",
            pipe_code="say_hello",
            blueprint=PipeLLMBlueprint(description="Greet the user.", output="native.Text", prompt="Say hello."),
        )
        pipe_error = StuffFactoryError("The pipe's own failure")
        mocker.patch.object(pipe_error, "to_error_report", side_effect=RuntimeError("The report could not be built"))
        empty_presence_scan = InputPresenceScan(missing_names=[], forced_absent=[], liftable=[])
        mocker.patch.object(PipeLLM, "validate_before_run", mocker.AsyncMock(return_value=empty_presence_scan))
        mocker.patch.object(PipeLLM, "live_run_pipe", mocker.AsyncMock(side_effect=pipe_error))
        mock_manager = mocker.MagicMock()
        mock_manager.on_pipe_start = mocker.MagicMock(return_value=("test-run:node_0", None))
        mocker.patch("pipelex.pipe_machinery.pipe_abstract.GraphTracerManager.get_instance", return_value=mock_manager)
        job_metadata = JobMetadata(
            run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="pytest", pipeline_run_id="test-run"),
            trace_context=make_trace_context(graph_id="test-run"),
        )

        with pytest.raises(StuffFactoryError) as exc_info:
            await pipe.run_pipe(
                job_metadata=job_metadata,
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParamsFactory.make_run_params(),
            )

        assert exc_info.value is pipe_error
        mock_manager.on_pipe_end_error.assert_called_once()
        end_kwargs = mock_manager.on_pipe_end_error.call_args.kwargs
        assert (end_kwargs["node_id"], end_kwargs["error_type"], end_kwargs["error_message"], end_kwargs["caller_facing"]) == (
            "test-run:node_0",
            "StuffFactoryError",
            str(pipe_error),
            False,
        )
