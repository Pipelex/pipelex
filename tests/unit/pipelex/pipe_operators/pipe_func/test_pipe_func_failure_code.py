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
from pipelex.errors.problem import ProblemView
from pipelex.graph.node_problem import make_node_problem
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
from tests.helpers.recovered_problem import make_recovered_function_raised


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
        # As the executor's own deadline raises it: the function and the limit it passed.
        raise PipeFuncExecutionError(msg).with_error_code(CoreCode.PIPE_FUNCTION_TIMED_OUT).with_params(function=function_name, timeout=30)

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


#: What a function's own text can quote: the run's input.
_FUNCTION_TEXT = "cannot file the note 'confidential-patient-diagnosis'"


class _OutOfProcessExecutor(PipeFuncExecutorProtocol):
    """An out-of-process executor reporting what the function raised as a coded Pipelex error, as its carrier rebuilds it.

    The far process's message holds the function's own text, and no exception of the function's rides as its cause.
    """

    def __init__(self, *, failure: Exception) -> None:
        self.failure = failure

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
        raise self.failure

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

        caller = failure.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.PIPE_FUNCTION_RAISED
        assert isinstance(failure.__cause__, PipeFuncRaisedError)
        assert type(failure.__cause__.__cause__).__name__ == raised_type
        assert f"Error: The function raised {raised_type}" in failure.message
        # What the function raised can quote the run's inputs or whatever the process holds: its class names it, and its
        # text reaches no view, the operator's included.
        function_text = str(failure.__cause__.__cause__)
        assert function_text not in failure.message
        assert raised_type not in str(caller.to_wire())
        operator = failure.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert operator.diagnostics.message == failure.message
        assert function_text not in str(operator.to_wire())

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

        assert failure.to_problem(view=ProblemView.CALLER).code == expected_code

    @pytest.mark.parametrize(
        ("failure", "expected_error"),
        [
            (PipeFuncRaisedError(f"KeyError: {_FUNCTION_TEXT}"), "Error: The function raised an exception"),
            (
                PipeFuncExecutionError(f"The function failed in the sandbox: {_FUNCTION_TEXT}"),
                "Error: PipeFuncExecutionError (runtime.unexpected)",
            ),
            (ConnectionResetError(f"The sandbox closed the call: {_FUNCTION_TEXT}"), "Error: ConnectionResetError"),
            (
                make_recovered_function_raised(
                    pipe="read_line", function="ledger_funcs.lines.read_line", message=f"The function raised in the sandbox: {_FUNCTION_TEXT}"
                ),
                "Error: RecoveredProblemError (pipe.function_raised)",
            ),
        ],
        ids=["function_raised_far_away", "coded_seam_failure", "foreign_transport_failure", "recovered_function_raised"],
    )
    @pytest.mark.asyncio
    async def test_an_out_of_process_failure_is_named_without_its_text(
        self,
        load_empty_library: Callable[[], str],
        mocker: MockerFixture,
        failure: Exception,
        expected_error: str,
    ) -> None:
        """Whatever an executor raised, its text can hold the function's own, which quotes the run's inputs: the step names its class."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)

        step_failure = await _failure_of(pipe_func=_make_pipe_func(), executor=_OutOfProcessExecutor(failure=failure), function=_raises_a_plain_error)

        assert step_failure.message.endswith(expected_error)
        assert _FUNCTION_TEXT not in step_failure.message

    @pytest.mark.asyncio
    async def test_a_function_that_raised_in_a_sandbox_is_the_step_s_traced_failure(
        self, load_empty_library: Callable[[], str], mocker: MockerFixture
    ) -> None:
        """The carrier of the sandbox's report declares `runtime.unexpected`: the step's trace record reads the code it carries."""
        load_empty_library()
        mocker.patch("pipelex.pipe_operators.func.pipe_func.is_pipe_func_sandbox_hosted", return_value=True)
        carrier = make_recovered_function_raised(pipe="read_line", function="ledger_funcs.lines.read_line")

        step_failure = await _failure_of(pipe_func=_make_pipe_func(), executor=_OutOfProcessExecutor(failure=carrier), function=_raises_a_plain_error)
        node_problem = make_node_problem(error=step_failure, pipe_code="read_line", pipe_path=["flow", "read_line"])

        assert step_failure.__cause__ is carrier
        assert node_problem.code == CoreCode.PIPE_FUNCTION_RAISED
        assert node_problem.location is not None
        assert node_problem.location.as_wire() == {"pipe": "read_line", "path": ["flow", "read_line"]}
        assert node_problem.diagnostics is None

    @pytest.mark.builds_problems_without_required_params(
        reason="the coercion of a function's return knows neither the step's output concept nor a field of it"
    )
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

        assert failure.to_problem(view=ProblemView.CALLER).code == CoreCode.PIPE_OUTPUT_INVALID
        assert isinstance(failure.__cause__, FuncOutputTypeError)
