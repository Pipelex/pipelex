from pathlib import Path
from typing import ClassVar

import pytest
from polyfactory.exceptions import FactoryException
from pytest_mock import MockerFixture

from pipelex.base_exceptions import ErrorDomain, PipelexError
from pipelex.core.exceptions import DryRunFailureErrorData
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.pipe_run.exceptions import DryRunError, PipeRouterError
from pipelex.pipeline.bundle_validator import (
    BundleValidator,
    DryRunOutput,
    DryRunStatus,
    _DryRunSweepRouter,  # pyright: ignore[reportPrivateUsage]
    _failing_pipe_recorder,  # pyright: ignore[reportPrivateUsage]
    _FailingPipeRecorder,  # pyright: ignore[reportPrivateUsage]
)
from pipelex.system.pipe_run_mode import PipeRunMode


class _CallerFacingMethodFaultError(PipelexError):
    error_domain = ErrorDomain.INPUT
    _authors_caller_facing_message: ClassVar[bool] = True


class _StorageFaultError(PipelexError):
    error_domain = ErrorDomain.CONFIG


class TestDryRunFailureLocation:
    def _make_pipe(self, mocker: MockerFixture, *, pipe_ref: str):
        domain_code, code = pipe_ref.rsplit(".", maxsplit=1)
        pipe = mocker.MagicMock()
        pipe.code = code
        pipe.domain_code = domain_code
        pipe.pipe_ref = pipe_ref
        return pipe

    def test_the_innermost_failing_pipe_is_found_through_the_cause_chain(self, mocker: MockerFixture) -> None:
        """A controller failing because a pipe it ran failed is attributed to that pipe, however it was wrapped."""
        inner_pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        outer_pipe = self._make_pipe(mocker, pipe_ref="board.run_workshop")
        inner_error = _CallerFacingMethodFaultError("the combine failed")
        outer_error = PipeRouterError(message="the step failed", run_mode=PipeRunMode.DRY, pipe_code="run_workshop", output_name=None, pipe_stack=[])
        outer_error.__cause__ = inner_error

        recorder = _FailingPipeRecorder(tolerated_pipe_refs=frozenset())
        recorder.record(error=inner_error, pipe=inner_pipe)
        recorder.record(error=outer_error, pipe=outer_pipe)

        assert recorder.find_failing_pipe(error=outer_error) is inner_pipe
        assert recorder.find_failing_pipe(error=_CallerFacingMethodFaultError("unrelated")) is None

    def test_a_failure_at_a_pipe_allowed_to_fail_is_noted_at_the_next_pipe_outward(self, mocker: MockerFixture) -> None:
        """However deep the controllers, a tolerated pipe's failure is noted once, at the innermost pipe that may not fail."""
        tolerated_pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        middle_pipe = self._make_pipe(mocker, pipe_ref="board.run_workshop")
        outer_pipe = self._make_pipe(mocker, pipe_ref="board.host_workshop")
        inner_error = _CallerFacingMethodFaultError("the combine failed")
        middle_error = PipeRouterError(message="the step failed", run_mode=PipeRunMode.DRY, pipe_code="run_workshop", output_name=None, pipe_stack=[])
        middle_error.__cause__ = inner_error

        recorder = _FailingPipeRecorder(tolerated_pipe_refs=frozenset(["board.analyze_topic"]))
        recorder.record(error=inner_error, pipe=tolerated_pipe)
        recorder.record(error=middle_error, pipe=middle_pipe)
        recorder.record(error=middle_error, pipe=outer_pipe)

        assert recorder.find_failing_pipe(error=middle_error) is middle_pipe
        assert recorder.find_failing_pipe(error=inner_error) is None

    @pytest.mark.asyncio
    async def test_the_sweep_router_notes_the_pipe_a_failure_left(self, mocker: MockerFixture) -> None:
        pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        failure = _CallerFacingMethodFaultError("the combine failed")
        mocker.patch.object(_DryRunSweepRouter, "_run_pipe_job", side_effect=failure)
        pipe_job = mocker.MagicMock()
        pipe_job.pipe = pipe
        recorder = _FailingPipeRecorder(tolerated_pipe_refs=frozenset())
        token = _failing_pipe_recorder.set(recorder)
        try:
            with pytest.raises(_CallerFacingMethodFaultError):
                await _DryRunSweepRouter().run(pipe_job)
        finally:
            _failing_pipe_recorder.reset(token)

        assert recorder.find_failing_pipe(error=failure) is pipe

    @pytest.mark.parametrize(
        ("error", "expected_text"),
        [
            (_CallerFacingMethodFaultError("branch 'ideas' is plural"), "branch 'ideas' is plural"),
            (_StorageFaultError("bucket s3://internal-bucket refused the write"), _StorageFaultError.title()),
            (PipeRunError(message="expression rendered nothing", run_mode=PipeRunMode.DRY, pipe_code="route"), PipeRunError.title()),
            (FactoryException("polyfactory internals"), "The dry run could not generate mock data for this pipe"),
        ],
        ids=["caller_facing", "config_fault", "not_caller_facing", "foreign"],
    )
    @pytest.mark.asyncio
    async def test_a_failure_keeps_its_text_only_when_it_is_caller_facing(self, mocker: MockerFixture, error: Exception, expected_text: str) -> None:
        mocker.patch("pipelex.pipeline.bundle_validator.get_telemetry_manager")
        mocker.patch("pipelex.pipeline.bundle_validator.get_config").return_value.inference.dry_run.allowed_to_fail_pipes = ["board.analyze_topic"]
        mocker.patch("pipelex.pipeline.bundle_validator.prepare_pipe_job")
        pipe_run = mocker.MagicMock()
        pipe_run.run = mocker.AsyncMock(side_effect=error)
        mocker.patch("pipelex.pipeline.bundle_validator.PipeRun", return_value=pipe_run)
        pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        pipe.is_signature = False

        results = await BundleValidator().validate_pipes([pipe], library_id="lib-1")

        failure = results["board.analyze_topic"].failure
        assert failure is not None
        assert (failure.pipe_code, failure.domain_code) == ("analyze_topic", "board")
        assert failure.message == f"Pipe 'analyze_topic' failed its dry run: {expected_text}"

    def test_a_failure_reached_through_a_controller_is_kept_once_its_own_preferred(self) -> None:
        inner_failure_via_outer = DryRunFailureErrorData(pipe_code="analyze_topic", domain_code="board", message="via the sequence")
        inner_failure_own = DryRunFailureErrorData(pipe_code="analyze_topic", domain_code="board", message="its own")
        other_failure = DryRunFailureErrorData(pipe_code="publish", domain_code="board", message="publish failed")
        unexpected_failures = {
            "board.run_workshop": DryRunOutput(
                pipe_code="run_workshop", pipe_ref="board.run_workshop", status=DryRunStatus.FAILURE, failure=inner_failure_via_outer
            ),
            "board.publish": DryRunOutput(pipe_code="publish", pipe_ref="board.publish", status=DryRunStatus.FAILURE, failure=other_failure),
            "board.analyze_topic": DryRunOutput(
                pipe_code="analyze_topic", pipe_ref="board.analyze_topic", status=DryRunStatus.FAILURE, failure=inner_failure_own
            ),
        }

        failures = BundleValidator._located_failures(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            unexpected_failures=unexpected_failures
        )

        assert failures == [inner_failure_own, other_failure]

    @pytest.mark.asyncio
    async def test_a_failure_met_at_a_pipe_allowed_to_fail_stays_on_the_swept_pipe(self, mocker: MockerFixture) -> None:
        """The tolerated pipe is not the failure: the swept pipe that failed because of it is."""
        mocker.patch("pipelex.pipeline.bundle_validator.get_telemetry_manager")
        mocker.patch("pipelex.pipeline.bundle_validator.get_config").return_value.inference.dry_run.allowed_to_fail_pipes = ["board.analyze_topic"]
        mocker.patch("pipelex.pipeline.bundle_validator.prepare_pipe_job")
        inner_pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        failure = _CallerFacingMethodFaultError("the combine failed")

        def _fail_inside_the_inner_pipe(_pipe_job: object) -> None:
            recorder = _failing_pipe_recorder.get()
            assert recorder is not None
            recorder.record(error=failure, pipe=inner_pipe)
            raise failure

        pipe_run = mocker.MagicMock()
        pipe_run.run = mocker.AsyncMock(side_effect=_fail_inside_the_inner_pipe)
        mocker.patch("pipelex.pipeline.bundle_validator.PipeRun", return_value=pipe_run)
        outer_pipe = self._make_pipe(mocker, pipe_ref="board.run_workshop")
        outer_pipe.is_signature = False

        with pytest.raises(DryRunError) as exc_info:
            await BundleValidator().validate_pipes([outer_pipe], library_id="lib-1")

        (located_failure,) = exc_info.value.failures
        assert (located_failure.pipe_code, located_failure.domain_code) == ("run_workshop", "board")

    @pytest.mark.asyncio
    async def test_a_source_the_library_manager_gives_as_a_path_is_kept_as_text(self, mocker: MockerFixture) -> None:
        """Injected managers written against the previous protocol may still return ``Path``."""
        mocker.patch("pipelex.pipeline.bundle_validator.get_telemetry_manager")
        mocker.patch("pipelex.pipeline.bundle_validator.get_config").return_value.inference.dry_run.allowed_to_fail_pipes = ["board.analyze_topic"]
        mocker.patch("pipelex.pipeline.bundle_validator.prepare_pipe_job")
        mocker.patch("pipelex.pipeline.bundle_validator.get_library_manager").return_value.get_pipe_source.return_value = Path("board.mthds")
        pipe_run = mocker.MagicMock()
        pipe_run.run = mocker.AsyncMock(side_effect=_CallerFacingMethodFaultError("the combine failed"))
        mocker.patch("pipelex.pipeline.bundle_validator.PipeRun", return_value=pipe_run)
        pipe = self._make_pipe(mocker, pipe_ref="board.analyze_topic")
        pipe.is_signature = False

        results = await BundleValidator().validate_pipes([pipe], library_id="lib-1")

        failure = results["board.analyze_topic"].failure
        assert failure is not None
        assert failure.source == "board.mthds"
