from collections.abc import Sequence
from typing import TYPE_CHECKING, cast

import pytest
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import CogtError, InferenceErrorCategory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.observer.observer_protocol import ObserverNoOp
from pipelex.pipe_run.exceptions import PipeRouterError, PipeRunError
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_router_protocol import PipeRouterProtocol
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipe_run.pipe_run_params_factory import PipeRunParamsFactory
from pipelex.pipe_run.transient_retry import TransientRetrySettings
from pipelex.pipeline.job_metadata import JobMetadata

if TYPE_CHECKING:
    from pipelex.core.pipes.pipe_abstract import PipeAbstract


class _StubPipe:
    """Minimal pipe stand-in: the router only reads `.code` off it."""

    code = "stub_pipe"


class _StubPipeRouter(PipeRouterProtocol):
    """Router whose `_run_pipe_job` raises a scripted sequence of errors then succeeds."""

    def __init__(
        self,
        failures: Sequence[Exception],
        transient_retry_settings: TransientRetrySettings,
        final_output: PipeOutput | None = None,
    ):
        self.observer = ObserverNoOp()
        self.transient_retry_settings = transient_retry_settings
        self._failures = failures
        self._final_output = final_output
        self.call_count = 0

    @override
    async def _run_pipe_job(self, pipe_job: PipeJob) -> PipeOutput:
        index = self.call_count
        self.call_count += 1
        if index < len(self._failures):
            raise self._failures[index]
        if self._final_output is None:
            msg = "stub router ran out of scripted failures with no final output"
            raise RuntimeError(msg)
        return self._final_output


def _make_pipe_job() -> PipeJob:
    return PipeJob.model_construct(
        pipe=cast("PipeAbstract", _StubPipe()),
        working_memory=None,
        working_memory_raw=None,
        pipe_run_params=PipeRunParamsFactory.make_run_params(pipe_run_mode=PipeRunMode.LIVE),
        job_metadata=JobMetadata(user_id="test-user", pipeline_run_id="test-run"),
        output_name=None,
        library_crate=None,
    )


def _make_retry_settings(max_transient_retries: int) -> TransientRetrySettings:
    return TransientRetrySettings(
        max_transient_retries=max_transient_retries,
        base_wait=1.0,
        max_wait=100.0,
        backoff_multiplier=2.0,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipeRouterRetry:
    async def test_transient_error_retries_then_reraises_last_error(self, mocker: MockerFixture) -> None:
        """A TRANSIENT CogtError retries up to max_transient_retries, then re-raises the last error as-is."""
        sleep_calls: list[float] = []

        def _fake_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep", side_effect=_fake_sleep)

        last_error = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        failures = [
            CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT),
            CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT),
            CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT),
            last_error,
        ]
        router = _StubPipeRouter(failures=failures, transient_retry_settings=_make_retry_settings(3))
        before_spy = mocker.spy(router, "_before_run")
        after_failing_spy = mocker.spy(router, "_after_failing_run")

        with pytest.raises(CogtError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is last_error
        assert router.call_count == 4
        assert len(sleep_calls) == 3
        assert before_spy.call_count == 1
        assert after_failing_spy.call_count == 1

    async def test_backoff_wait_increases_each_attempt(self, mocker: MockerFixture) -> None:
        """Successive retry waits grow with the exponential backoff multiplier."""
        sleep_calls: list[float] = []

        def _fake_sleep(duration: float) -> None:
            sleep_calls.append(duration)

        mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep", side_effect=_fake_sleep)
        warning_mock = mocker.patch.object(log, "warning")

        failures = [CogtError(message="boom", error_category=InferenceErrorCategory.TRANSIENT) for _ in range(10)]
        router = _StubPipeRouter(failures=failures, transient_retry_settings=_make_retry_settings(3))

        with pytest.raises(CogtError):
            await router.run(_make_pipe_job())

        assert sleep_calls == [1.0, 2.0, 4.0]
        assert warning_mock.call_count == 3
        first_warning = str(warning_mock.call_args_list[0].args[0])
        assert "1/3" in first_warning
        assert InferenceErrorCategory.TRANSIENT in first_warning

    @pytest.mark.parametrize(
        "error_category",
        [
            InferenceErrorCategory.CONFIGURATION,
            InferenceErrorCategory.CONTENT,
            InferenceErrorCategory.CAPACITY,
            InferenceErrorCategory.UNKNOWN,
        ],
    )
    async def test_non_retryable_category_fails_immediately(
        self,
        mocker: MockerFixture,
        error_category: InferenceErrorCategory,
    ) -> None:
        """A non-retryable CogtError category fails on the first attempt with no retry."""
        sleep_mock = mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        error = CogtError(message="nope", error_category=error_category)
        router = _StubPipeRouter(failures=[error, error, error, error], transient_retry_settings=_make_retry_settings(3))
        after_failing_spy = mocker.spy(router, "_after_failing_run")

        with pytest.raises(CogtError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is error
        assert router.call_count == 1
        assert sleep_mock.call_count == 0
        assert after_failing_spy.call_count == 1

    async def test_max_transient_retries_zero_disables_retry(self, mocker: MockerFixture) -> None:
        """max_transient_retries = 0 is an explicit opt-out: a TRANSIENT error is not retried."""
        sleep_mock = mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        error = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
        router = _StubPipeRouter(failures=[error, error], transient_retry_settings=_make_retry_settings(0))

        with pytest.raises(CogtError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value is error
        assert router.call_count == 1
        assert sleep_mock.call_count == 0

    async def test_pipe_run_error_still_wraps_as_pipe_router_error(self, mocker: MockerFixture) -> None:
        """A PipeRunError with no retryable CogtError cause is not retried and still wraps as PipeRouterError."""
        sleep_mock = mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        pipe_run_error = PipeRunError(message="bad pipe", run_mode=PipeRunMode.LIVE, pipe_code="stub_pipe")
        router = _StubPipeRouter(failures=[pipe_run_error, pipe_run_error], transient_retry_settings=_make_retry_settings(3))
        after_failing_spy = mocker.spy(router, "_after_failing_run")

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert exc_info.value.__cause__ is pipe_run_error
        assert router.call_count == 1
        assert sleep_mock.call_count == 0
        assert after_failing_spy.call_count == 1

    async def test_transient_error_retries_then_succeeds(self, mocker: MockerFixture) -> None:
        """When a retry succeeds within budget, the router returns the output normally."""
        mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        expected_output = PipeOutput()
        failures = [
            CogtError(message="transient", error_category=InferenceErrorCategory.TRANSIENT),
            CogtError(message="transient", error_category=InferenceErrorCategory.TRANSIENT),
        ]
        router = _StubPipeRouter(
            failures=failures,
            transient_retry_settings=_make_retry_settings(3),
            final_output=expected_output,
        )

        result = await router.run(_make_pipe_job())

        assert result is expected_output
        assert router.call_count == 3

    async def test_pipe_run_error_wrapping_transient_cogt_error_retries(self, mocker: MockerFixture) -> None:
        """A PipeRunError whose __cause__ is a TRANSIENT CogtError is retried, then wrapped.

        This is the LLM-operator path: PipeLLM / PipeStructure wrap the worker's
        LLMCompletionError into a PipeRunError, so the retryable CogtError reaches
        the router as the `__cause__` of a PipeRunError rather than as a raw CogtError.
        These tests drive `_run_pipe_job` directly; end-to-end coverage through a real
        operator lives in tests/integration/pipelex/pipes/operator/test_operator_transient_retry.py.
        """
        sleep_mock = mocker.patch("pipelex.pipe_run.pipe_router_protocol.asyncio.sleep")

        def _wrapped_transient() -> PipeRunError:
            cogt_error = CogtError(message="rate limited", error_category=InferenceErrorCategory.TRANSIENT)
            pipe_run_error = PipeRunError(message="operator wrap", run_mode=PipeRunMode.LIVE, pipe_code="stub_pipe")
            pipe_run_error.__cause__ = cogt_error
            return pipe_run_error

        failures = [_wrapped_transient() for _ in range(4)]
        router = _StubPipeRouter(failures=failures, transient_retry_settings=_make_retry_settings(3))

        with pytest.raises(PipeRouterError) as exc_info:
            await router.run(_make_pipe_job())

        assert router.call_count == 4
        assert sleep_mock.call_count == 3
        wrapped_cause = exc_info.value.__cause__
        assert wrapped_cause is failures[-1]
        assert isinstance(wrapped_cause, PipeRunError)
        assert isinstance(wrapped_cause.__cause__, CogtError)
