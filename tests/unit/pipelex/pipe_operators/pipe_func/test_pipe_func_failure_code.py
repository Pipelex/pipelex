from collections.abc import Callable
from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture
from typing_extensions import override

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.stuffs.text_content import TextContent
from pipelex.errors.error_codes import ErrorCode
from pipelex.interpreter_hub import scoped_pipe_func_executor
from pipelex.kernel.exceptions import FuncOutputTypeError
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipe_operators.func.direct_pipe_func_executor import DirectPipeFuncExecutor
from pipelex.pipe_operators.func.exceptions import PipeFuncExecutionError, PipeFuncRaisedError
from pipelex.pipe_operators.func.pipe_func import PipeFunc
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.func.pipe_func_call_context import pipe_func_call_in_flight
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest, PipeFuncExecutionResponse
from pipelex.pipe_operators.func.pipe_func_executor_protocol import PipeFuncExecutionResult, PipeFuncExecutorProtocol
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.exceptions import RunParameterError
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.storage.exceptions import StorageS3Error


def _raises_a_request_refusal(working_memory: WorkingMemory) -> TextContent:
    """A function whose own code calls a helper that refuses a run parameter."""
    _ = working_memory
    msg = "The storage scope 'elsewhere' is outside the read scope"
    raise RunParameterError(msg)


def _raises_a_storage_outage(working_memory: WorkingMemory) -> TextContent:
    _ = working_memory
    msg = "The storage could not be reached"
    raise StorageS3Error(msg)


def _raises_a_plain_error(working_memory: WorkingMemory) -> TextContent:
    _ = working_memory
    msg = "the ledger has no line for this parcel"
    raise KeyError(msg)


def _returns_a_list_holding_a_dict(working_memory: WorkingMemory) -> list[dict[str, str]]:
    _ = working_memory
    return [{"parcel": "7"}]


def _returns_a_list_holding_a_number(working_memory: WorkingMemory) -> list[Any]:
    _ = working_memory
    return [TextContent(text="line 7"), 7]


class _TimedOutExecutor(PipeFuncExecutorProtocol):
    """An executor whose own seam fails: the function ran past its timeout."""

    @override
    async def run_pipe_func(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_code: str,
        function_name: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> PipeFuncExecutionResult:
        msg = f"PipeFunc '{function_name}' exceeded its 30s timeout"
        raise PipeFuncExecutionError(msg).with_error_code(CoreCode.PIPE_FUNCTION_TIMED_OUT)

    @override
    async def run_pipe_func_transported(self, *, request: PipeFuncExecutionRequest) -> PipeFuncExecutionResponse:
        msg = "Not used by this test"
        raise NotImplementedError(msg)


class _TransportFailingExecutor(PipeFuncExecutorProtocol):
    """An out-of-process executor whose transport failed with an exception that is not a Pipelex error."""

    @override
    async def run_pipe_func(
        self,
        *,
        job_metadata: JobMetadata,
        pipe_code: str,
        function_name: str,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
    ) -> PipeFuncExecutionResult:
        msg = "The connection to the sandbox was reset"
        raise ConnectionResetError(msg)

    @override
    async def run_pipe_func_transported(self, *, request: PipeFuncExecutionRequest) -> PipeFuncExecutionResponse:
        msg = "Not used by this test"
        raise NotImplementedError(msg)


def _make_pipe_func() -> PipeFunc:
    blueprint = PipeFuncBlueprint(
        description="Read the parcel's line in the ledger",
        inputs={},
        output="native.Text",
        function_name="ledger_funcs.lines.read_line",
    )
    return PipeFactory[PipeFunc].make_from_blueprint(domain_code="failure_code", pipe_code="read_line", blueprint=blueprint)


async def _failure_of(*, pipe_func: PipeFunc, executor: PipeFuncExecutorProtocol, function: Callable[..., Any]) -> PipeRunError:
    job_metadata = JobMetadata(run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run"))
    with (
        scoped_pipe_func_executor(pipe_func_executor=executor),
        pipe_func_call_in_flight(pipe_ref=pipe_func.pipe_ref, function=function),
        pytest.raises(PipeRunError) as exc_info,
    ):
        await pipe_func._live_run_operator_pipe(  # ruff: ignore[private-member-access] # pyright: ignore[reportPrivateUsage]
            job_metadata=job_metadata,
            working_memory=WorkingMemoryFactory.make_empty(),
            pipe_run_params=PipeRunParams(run_mode=PipeRunMode.LIVE, pipe_stack_limit=10, batch_max_concurrency=None),
        )
    return exc_info.value


class TestPipeFuncFailureCode:
    @pytest.mark.parametrize(
        ("function", "raised_type"),
        [
            (_raises_a_request_refusal, "RunParameterError"),
            (_raises_a_storage_outage, "StorageS3Error"),
            (_raises_a_plain_error, "KeyError"),
        ],
        ids=["coded_request_refusal", "coded_storage_outage", "plain_exception"],
    )
    @pytest.mark.asyncio
    async def test_what_the_function_raised_is_the_functions_failure(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture, function: Callable[..., Any], raised_type: str
    ) -> None:
        """A coded Pipelex error a helper raised inside the function is still the function's failure, and rides as the cause."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        failure = await _failure_of(pipe_func=_make_pipe_func(), executor=DirectPipeFuncExecutor(), function=function)

        assert failure.to_error_report().code == CoreCode.PIPE_FUNCTION_RAISED
        assert isinstance(failure.__cause__, PipeFuncRaisedError)
        assert type(failure.__cause__.__cause__).__name__ == raised_type
        assert f"Error: {raised_type}: " in failure.message

    @pytest.mark.parametrize(
        ("executor", "expected_code"),
        [
            (_TimedOutExecutor(), CoreCode.PIPE_FUNCTION_TIMED_OUT),
            (_TransportFailingExecutor(), CoreCode.RUNTIME_UNEXPECTED),
        ],
        ids=["timed_out", "foreign_transport_failure"],
    )
    @pytest.mark.asyncio
    async def test_a_failure_of_the_executor_keeps_its_own_code(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
        executor: PipeFuncExecutorProtocol,
        expected_code: ErrorCode,
    ) -> None:
        """A failure of the seam is not the function's, and an exception no executor marked proves nothing about the function."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        failure = await _failure_of(pipe_func=_make_pipe_func(), executor=executor, function=_raises_a_plain_error)

        assert failure.to_error_report().code == expected_code

    @pytest.mark.parametrize(
        "function",
        [_returns_a_list_holding_a_dict, _returns_a_list_holding_a_number],
        ids=["list_holding_a_dict", "list_holding_a_number"],
    )
    @pytest.mark.asyncio
    async def test_a_return_shape_the_coercion_refuses_is_the_step_s_output_failing(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture, function: Callable[..., Any]
    ) -> None:
        """The function returned, so what it returned failing the coercion is no failure of the function's, whatever its shape."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        failure = await _failure_of(pipe_func=_make_pipe_func(), executor=DirectPipeFuncExecutor(), function=function)

        assert failure.to_error_report().code == CoreCode.PIPE_OUTPUT_INVALID
        assert isinstance(failure.__cause__, FuncOutputTypeError)
