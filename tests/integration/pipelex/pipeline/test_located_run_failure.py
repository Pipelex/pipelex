from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.base_exceptions import INTERNAL_ERROR_PLACEHOLDER, DisclosureMode, ErrorReport, PipelexError
from pipelex.config import get_config
from pipelex.pipe_run.exceptions import PipeRouterError, find_failure_location
from pipelex.pipe_run.pipe_router import PipeRouter
from pipelex.pipe_run.pipe_run import PipeRun
from pipelex.pipe_run.pipe_run_protocol import PipeRunProtocol
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_bridge.direct_orchestrator import DirectOrchestrator
from pipelex.runtime_bridge.exceptions import PipelexBridgeDispatchError
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipeline.test_data import LocatedRunFailureTestData

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_output import PipeOutput
    from pipelex.pipe_run.delivery_assignment import DeliveryAssignment
    from pipelex.pipe_run.pipe_job import PipeJob
    from pipelex.system.configuration.configs import PipelineExecutionConfig


def _dry_mock_config() -> PipelineExecutionConfig:
    return get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=False,
        mock_inputs=True,
    )


class _DirectOrchestratorPipeRun(PipeRunProtocol):
    """Dispatch through the in-process orchestrator, as the API runner's `/execute` does in `direct` mode."""

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        await DirectOrchestrator().execute(pipe_job=pipe_job, delivery_assignment=delivery_assignment)
        msg = "This adapter only serves failing runs."
        raise AssertionError(msg)


class _RecoveredReportError(PipelexError):
    """Carries a report recovered across a transport boundary, as a distributed submitter does."""

    def __init__(self, message: str, *, error_report: ErrorReport):
        super().__init__(message)
        self.error_report = error_report

    @override
    def to_error_report(self) -> ErrorReport:
        return self.error_report


class _RecoveredReportPipeRun(PipeRunProtocol):
    """Fail the way a distributed orchestrator does: its bridge sentence around a recovered report."""

    def __init__(self, *, recovered_report: ErrorReport):
        self._recovered_report = recovered_report

    @override
    async def run(self, pipe_job: PipeJob, *, delivery_assignment: DeliveryAssignment | None = None) -> PipeOutput:
        recovered = _RecoveredReportError(self._recovered_report.message, error_report=self._recovered_report)
        msg = f"Pipe execution failed in temporal blocking delivery for pipe '{pipe_job.pipe.code}': {recovered}"
        raise PipelexBridgeDispatchError(msg) from recovered


class _ForeignFailureRouter(PipeRouter):
    """A router whose pipe raises an exception that is not a PipelexError."""

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        msg = "boom from a pipe"
        raise KeyError(msg)


@pytest.mark.asyncio(loop_scope="class")
class TestLocatedRunFailure:
    async def _run_parallel_failure(self, *, pipe_run: PipeRunProtocol | None = None) -> PipelineExecutionError:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=_dry_mock_config(), pipe_run=pipe_run)
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="flow", mthds_contents=[LocatedRunFailureTestData.PARALLEL_MTHDS])
        return exc_info.value

    async def test_unserved_model_is_reported_at_the_failing_step(self) -> None:
        """The model example: the failing step, its path and the model error's own identity and sentence."""
        runner = PipelexMTHDSProtocol()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="two_steps", mthds_contents=[LocatedRunFailureTestData.MODEL_MTHDS], inputs={"topic": "cats"})
        error = exc_info.value

        assert error.pipe_code == "summarize"
        assert error.pipe_stack == ["two_steps", "summarize"]

        report = error.to_error_report()
        assert report.error_type == "ModelNotFoundError"
        assert report.title == "Model not found"
        assert report.type_uri.endswith("/model-not-found-error/")
        unserved_handle = LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE
        assert report.message == f"Pipe 'summarize' failed (two_steps → summarize): Model handle '{unserved_handle}' was not found in the model deck."
        # The local-deck remedy is the local CLI's to give: the message reaches hosted readers too.
        assert ".pipelex/inference" not in report.message
        assert "pipelex init" not in report.message
        assert report.model == LocatedRunFailureTestData.UNSERVED_MODEL_HANDLE
        # Nothing on the chain advises an action, so the fallback names the failing pipe.
        assert report.user_action is not None
        assert report.user_action.detail == "The run failed in pipe 'summarize': the message gives the cause."

        # The step names the model in an inline setting, and no entry of the deck names it: the
        # caller's own fault, whose message STRICT disclosure keeps.
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["message"] == report.message
        assert strict_payload["error_domain"] == "input"
        assert strict_payload["error_type"] == "ModelNotFoundError"

    async def test_parallel_combine_failure_is_reported_at_the_nested_parallel(self) -> None:
        """The multiplicity example: the parallel nested in the sequence, with the combine's own identity and message."""
        error = await self._run_parallel_failure()

        assert error.pipe_code == "analyze"
        assert error.pipe_stack == ["flow", "analyze"]

        report = error.to_error_report()
        assert report.error_type == "StuffFactoryError"
        assert report.message.startswith("Pipe 'analyze' failed (flow → analyze): Error combining stuffs for concept Report")
        assert "expected located_failure_parallel__Idea, got ListContent" in report.message
        # The combine's own next step, since a mismatched combine is the caller's to fix.
        assert report.user_action is not None
        assert report.user_action.detail.startswith("Change the method so that each branch of PipeParallel 'analyze' produces")

    async def test_caller_facing_root_keeps_its_message_under_strict(self) -> None:
        """A caller-facing root fault keeps its own message, located, under STRICT."""
        runner = PipelexMTHDSProtocol()
        with pytest.raises(PipelineExecutionError) as exc_info:
            await runner.execute(pipe_code="force_flow", mthds_contents=[LocatedRunFailureTestData.FORCE_MTHDS], inputs={})
        error = exc_info.value

        assert error.pipe_code == "force_echo"
        assert error.pipe_stack == ["force_flow", "force_echo"]

        report = error.to_error_report()
        assert report.error_type == "OptionalValueAbsentError"
        assert report.caller_facing_message is True
        strict_payload = report.to_dict(disclosure_mode=DisclosureMode.STRICT)
        assert strict_payload["message"] == report.message
        assert strict_payload["message"].startswith("Pipe 'force_echo' failed (force_flow → force_echo): ")
        assert "clause" in strict_payload["message"]

    async def test_in_process_orchestrator_adds_nothing(self) -> None:
        """Through the in-process bridge, the report and the location are the direct run's; the bridge's sentence is in neither."""
        direct_error = await self._run_parallel_failure()
        bridged_error = await self._run_parallel_failure(pipe_run=_DirectOrchestratorPipeRun())

        assert isinstance(bridged_error.__cause__, PipelexBridgeDispatchError)
        assert bridged_error.pipe_code == direct_error.pipe_code
        assert bridged_error.pipe_stack == direct_error.pipe_stack
        assert bridged_error.message == direct_error.message
        assert bridged_error.to_error_report() == direct_error.to_error_report()
        assert "DIRECT mode" not in bridged_error.to_error_report().message

    async def test_recovered_report_adds_nothing(self) -> None:
        """A report recovered across a transport boundary, as the hosted run stores it, reads as the direct run's."""
        direct_error = await self._run_parallel_failure()
        location = find_failure_location(error=direct_error)
        assert isinstance(location, PipeRouterError)
        # What a distributed worker's run root stores: the located router error's report.
        recovered_report = location.to_error_report()

        bridged_error = await self._run_parallel_failure(pipe_run=_RecoveredReportPipeRun(recovered_report=recovered_report))

        assert bridged_error.to_error_report() == direct_error.to_error_report()
        assert "temporal blocking delivery" not in bridged_error.to_error_report().message
        assert "temporal blocking delivery" not in bridged_error.message

    async def test_foreign_exception_is_located_as_unexpected_error(self) -> None:
        """A non-PipelexError raised in a pipe's run comes out located, as a PipelexUnexpectedError naming its class."""
        error = await self._run_parallel_failure(pipe_run=PipeRun(pipe_router=_ForeignFailureRouter()))

        assert error.pipe_code == "flow"
        assert error.pipe_stack == ["flow"]
        report = error.to_error_report()
        assert report.error_type == "PipelexUnexpectedError"
        assert report.message == "Pipe 'flow' failed: KeyError: 'boom from a pipe'"
        assert report.caller_facing_message is False
        assert report.to_dict(disclosure_mode=DisclosureMode.STRICT)["message"] == INTERNAL_ERROR_PLACEHOLDER
