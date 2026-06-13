"""Error-path coverage for :meth:`PipelexMTHDSProtocol.execute`.

Pins the ``except PipelexError`` arms (wrap-with-job vs propagate-unwrapped-without-job)
and the ``except ValidationError`` arm. The happy path, the ``PipeRouterError`` wrap, and
the finally-block library-restore matrix are pinned by the integration suite
(``tests/integration/pipelex/pipeline/``) and are deliberately not re-tested here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

import pytest
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import PipeExecutionError, PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.telemetry.events import EventName, EventProperty, Outcome
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pytest_mock import MockerFixture, MockType

    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob


class _MiniPayload(BaseModel):
    """Minimal model used to capture a genuine pydantic ValidationError."""

    count: int


class _RaisingPipeRun(PipeRunProtocol):
    """A PipeRun whose ``run`` always raises the injected exception."""

    def __init__(self, exc: Exception):
        self._exc = exc

    @override
    async def run(self, pipe_job: PipeJob, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        raise self._exc


class _ExecuteEnv(NamedTuple):
    setup_mock: MockType
    telemetry_manager: MockType
    pipe_job: MockType
    execution_config: MockType


_RUN_ID = "run-id-123"
_LIB_ID = "lib-id-456"


@pytest.mark.asyncio(loop_scope="class")
class TestRunnerExecuteErrorPaths:
    def _patch_env(self, mocker: MockerFixture) -> _ExecuteEnv:
        """Patch the hub getters and ``pipeline_run_setup`` at the runner namespace.

        The execution_config stub disables graph and usage generation so the
        finally block stays inert apart from the (mocked) registry/library cleanup.
        """
        pipe_job = mocker.MagicMock(name="pipe_job")
        pipe_job.pipe.code = "echo_pipe"
        pipe_job.pipe.pipe_type = "PipeLLM"
        pipe_job.pipe_run_params.run_mode = PipeRunMode.DRY
        pipe_job.pipe_run_params.pipe_stack = ["root_pipe", "echo_pipe"]
        pipe_job.output_name = "topic_out"

        setup_mock = mocker.patch(
            "pipelex.pipeline.runner.pipeline_run_setup",
            new=mocker.AsyncMock(return_value=(pipe_job, _RUN_ID, _LIB_ID)),
        )
        telemetry_manager = mocker.patch("pipelex.pipeline.runner.get_telemetry_manager").return_value
        mocker.patch("pipelex.pipeline.runner.get_report_delegate")
        mocker.patch("pipelex.pipeline.runner.get_pipeline_manager")
        mocker.patch("pipelex.pipeline.runner.get_library_manager")
        mocker.patch("pipelex.pipeline.runner.set_current_library")
        mocker.patch("pipelex.pipeline.runner.clear_current_library")
        mocker.patch("pipelex.pipeline.runner.get_current_library_id_or_none", return_value=None)

        execution_config = mocker.MagicMock(name="execution_config")
        execution_config.is_generate_graph = False
        execution_config.is_generate_usage = False
        return _ExecuteEnv(setup_mock=setup_mock, telemetry_manager=telemetry_manager, pipe_job=pipe_job, execution_config=execution_config)

    async def test_pipelex_error_with_resolved_job_wraps_into_pipeline_execution_error(self, mocker: MockerFixture) -> None:
        """A PipelexError raised by the pipe run AFTER setup resolved the job is wrapped
        into a PipelineExecutionError carrying the job's identity, and a FAILURE
        telemetry event fires.
        """
        env = self._patch_env(mocker)
        original = PipeExecutionError("boom from pipe")
        runner = PipelexMTHDSProtocol(
            execution_config=env.execution_config,
            pipe_run=_RaisingPipeRun(original),
        )

        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="echo_pipe")

        wrapped = exc_info.value
        assert wrapped.message == "boom from pipe"
        assert wrapped.pipe_code == "echo_pipe"
        assert wrapped.output_name == "topic_out"
        assert wrapped.run_mode == PipeRunMode.DRY
        assert wrapped.pipe_stack == ["root_pipe", "echo_pipe"]
        assert wrapped.__cause__ is original
        env.telemetry_manager.track_event.assert_called_once_with(
            event_name=EventName.PIPELINE_COMPLETE,
            properties={
                EventProperty.PIPELINE_RUN_ID: _RUN_ID,
                EventProperty.PIPE_TYPE: "PipeLLM",
                EventProperty.PIPELINE_OUTCOME: Outcome.FAILURE,
            },
        )

    async def test_pipelex_error_during_setup_propagates_unwrapped(self, mocker: MockerFixture) -> None:
        """When pipeline_run_setup itself raises (pipe_job is None), the SAME exception
        instance propagates unwrapped and no failure telemetry event fires.
        """
        env = self._patch_env(mocker)
        original = PipeExecutionError("setup exploded")
        env.setup_mock.side_effect = original
        runner = PipelexMTHDSProtocol(execution_config=env.execution_config)

        with pytest.raises(PipeExecutionError) as exc_info:
            await runner.execute(pipe_code="echo_pipe")

        assert exc_info.value is original
        assert exc_info.value.__cause__ is None
        env.telemetry_manager.track_event.assert_not_called()

    async def test_validation_error_wraps_into_pipe_execution_error(self, mocker: MockerFixture) -> None:
        """A pydantic ValidationError raised by the pipe run becomes a PipeExecutionError
        whose message names the failing model and embeds the formatted error.
        """
        env = self._patch_env(mocker)
        with pytest.raises(ValidationError) as validation_exc_info:
            _MiniPayload(count="not-a-number")  # pyright: ignore[reportArgumentType]
        validation_error = validation_exc_info.value
        runner = PipelexMTHDSProtocol(
            execution_config=env.execution_config,
            pipe_run=_RaisingPipeRun(validation_error),
        )

        with pytest.raises(PipeExecutionError) as exc_info:
            await runner.execute(pipe_code="echo_pipe")

        wrapped = exc_info.value
        assert wrapped.__cause__ is validation_error
        assert "Input validation failed for '_MiniPayload'" in wrapped.message
        assert format_pydantic_validation_error(validation_error) in wrapped.message
        env.telemetry_manager.track_event.assert_not_called()
