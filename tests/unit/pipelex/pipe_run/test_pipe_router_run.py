from typing import TYPE_CHECKING, cast

import pytest
from pydantic import BaseModel, ValidationError
from typing_extensions import override

from pipelex.base_exceptions import ErrorReport, PipelexError, PipelexUnexpectedError
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.pipe_machinery.pipe_abstract import PipeAbstract


class _StubPipe:
    """Minimal pipe stand-in: the router only reads `.code` off it."""

    code = "stub_pipe"


class _StubPipeRouter(PipeRouterProtocol):
    """Router whose `_run_pipe_job` always raises a scripted error and counts its calls."""

    def __init__(self, error: Exception):
        self.observer = ObserverNoOp()
        self._error = error
        self.call_count = 0

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        self.call_count += 1
        raise self._error


class _PassThroughRouter(_StubPipeRouter):
    """A host router that lets its runtime's RuntimeError through, as one does for a cancellation."""

    @override
    def _as_pipelex_failure(self, *, error: Exception) -> PipelexError | None:
        if isinstance(error, RuntimeError):
            return None
        return super()._as_pipelex_failure(error=error)


class _RecoveredReportCarrierError(PipelexError):
    """Carries a root fault's report recovered across a transport boundary."""

    def __init__(self, message: str, *, error_report: ErrorReport):
        super().__init__(message)
        self.error_report = error_report

    @override
    def to_error_report(self) -> ErrorReport:
        return self.error_report


class _RelocatingHostRouter(_StubPipeRouter):
    """A host router whose transport packed the root fault's report and the location found on the far side."""

    def __init__(self, error: Exception, *, packed_report: ErrorReport, packed_pipe_code: str, packed_pipe_stack: list[str]):
        super().__init__(error=error)
        self._packed_report = packed_report
        self._packed_pipe_code = packed_pipe_code
        self._packed_pipe_stack = packed_pipe_stack

    @override
    def _as_pipelex_failure(self, *, error: Exception) -> PipelexError | None:
        carrier = _RecoveredReportCarrierError(self._packed_report.message, error_report=self._packed_report)
        located = PipeRouterError.make_located(
            failure=carrier, run_mode=PipeRunMode.LIVE, pipe_code=self._packed_pipe_code, output_name=None, pipe_stack=self._packed_pipe_stack
        )
        located.__cause__ = carrier
        return located


class _MiniPayload(BaseModel):
    """Minimal model used to capture a genuine pydantic ValidationError."""

    count: int


def _make_pipe_job() -> PipeJob:
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", _StubPipe()),
        working_memory=None,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
        job_metadata=JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", user_id="test-user", pipeline_run_id="test-run")),
        output_name=None,
        library_crate=None,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRouterRun:
    async def test_transient_cogt_error_surfaces_on_first_attempt(self) -> None:
        """Direct execution is a single pipeline-level attempt: a transient CogtError is not retried.

        Pins the "direct = single attempt" contract against a future re-introduction of a retry loop.
        The error leaves located at the pipe, chained to the CogtError, and still reports as it.
        """
        error = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        router = _StubPipeRouter(error=error)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.__cause__ is error
        assert exc_info.value.to_error_report().error_type == "CogtError"
        assert exc_info.value.to_error_report().retryable is True
        assert router.call_count == 1

    async def test_pipe_run_error_wraps_as_pipe_router_error(self) -> None:
        """A PipeRunError surfaces as a PipeRouterError carrying the pipe-stack context.

        Pins the "keep the handler" contract against a future accidental deletion of the
        error-propagation handler in `run()`.
        """
        pipe_run_error = PipeRunError(message="bad pipe", run_mode=PipeRunMode.LIVE, pipe_code="stub_pipe")
        router = _StubPipeRouter(error=pipe_run_error)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.__cause__ is pipe_run_error
        assert exc_info.value.pipe_code == "stub_pipe"
        assert exc_info.value.pipe_stack == ["stub_pipe"]
        assert router.call_count == 1

    async def test_any_pipelex_error_is_located_with_its_own_report(self) -> None:
        """A PipelexError that is neither a CogtError nor a PipeRunError is located too, and reports as itself."""
        stuff_error = StuffFactoryError("Error combining stuffs")
        router = _StubPipeRouter(error=stuff_error)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        located = exc_info.value
        assert located.__cause__ is stuff_error
        assert located.pipe_code == "stub_pipe"
        assert located.pipe_stack == ["stub_pipe"]
        assert located.message == "Pipe 'stub_pipe' failed: Error combining stuffs"
        report = located.to_error_report()
        assert report.error_type == "StuffFactoryError"
        assert report.message == "Pipe 'stub_pipe' failed: Error combining stuffs"

    async def test_foreign_exception_is_located_as_unexpected_error(self) -> None:
        """A non-PipelexError is wrapped into a PipelexUnexpectedError naming its class, never caller-facing."""
        foreign_error = ValueError("unexpected value")
        router = _StubPipeRouter(error=foreign_error)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        unexpected = exc_info.value.__cause__
        assert isinstance(unexpected, PipelexUnexpectedError)
        assert unexpected.__cause__ is foreign_error
        assert unexpected.message == "ValueError: unexpected value"
        report = exc_info.value.to_error_report()
        assert report.error_type == "PipelexUnexpectedError"
        assert report.message == "Pipe 'stub_pipe' failed: ValueError: unexpected value"
        assert report.caller_facing_message is False

    async def test_pydantic_validation_error_keeps_its_readable_rendering(self) -> None:
        """A pydantic ValidationError is named and rendered the way the runner renders one."""
        with pytest.raises(ValidationError) as validation_info:
            _MiniPayload(count="not-a-number")  # pyright: ignore[reportArgumentType]
        router = _StubPipeRouter(error=validation_info.value)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        unexpected = exc_info.value.__cause__
        assert isinstance(unexpected, PipelexUnexpectedError)
        assert unexpected.message == f"ValidationError: {format_pydantic_validation_error(validation_info.value)}"

    async def test_already_located_failure_keeps_the_innermost_location(self) -> None:
        """A failure a router below already located passes through untouched: the innermost location wins."""
        inner_failure = PipeRouterError(
            message="Pipe 'inner' failed (outer → inner): boom",
            run_mode=PipeRunMode.LIVE,
            pipe_code="inner",
            output_name=None,
            pipe_stack=["outer", "inner"],
        )
        router = _StubPipeRouter(error=inner_failure)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is inner_failure

    async def test_a_host_router_rebuilding_the_far_location_is_not_located_again(self) -> None:
        """A located failure the hook rebuilds from a packed report and location passes through, located once."""
        root_report = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT).to_error_report()
        router = _RelocatingHostRouter(
            error=RuntimeError("child workflow failed"),
            packed_report=root_report,
            packed_pipe_code="leaf",
            packed_pipe_stack=["flow", "ctrl", "leaf"],
        )

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.pipe_code == "leaf"
        assert isinstance(exc_info.value.__cause__, _RecoveredReportCarrierError)
        report = exc_info.value.to_error_report()
        assert report.error_type == "CogtError"
        assert report.message == "Pipe 'leaf' failed (flow → ctrl → leaf): rate limited"

    async def test_a_foreign_exception_raised_from_an_older_location_is_located_here(self) -> None:
        """A foreign exception raised from an earlier located failure is a new failure: converted and located at this pipe."""
        older_location = PipeRouterError(
            message="Pipe 'older_pipe' failed: combine failed",
            run_mode=PipeRunMode.LIVE,
            pipe_code="older_pipe",
            output_name=None,
            pipe_stack=["older_pipe"],
        )
        foreign_failure = KeyError("new failure")
        foreign_failure.__cause__ = older_location
        router = _StubPipeRouter(error=foreign_failure)

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.pipe_code == _StubPipe.code
        assert isinstance(exc_info.value.__cause__, PipelexUnexpectedError)
        assert exc_info.value.__cause__.__cause__ is foreign_failure
        assert exc_info.value.to_error_report().error_type == "PipelexUnexpectedError"

    async def test_a_host_router_can_let_a_failure_through(self) -> None:
        """A host router whose hook answers None sees its transport's exception propagate unchanged."""
        control_flow_error = RuntimeError("cancelled by the host runtime")
        router = _PassThroughRouter(error=control_flow_error)

        with pytest.raises(RuntimeError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is control_flow_error
