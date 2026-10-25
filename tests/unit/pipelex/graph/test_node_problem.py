import logging

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.exceptions import InferenceErrorCategory, LLMCompletionError
from pipelex.core.pipes.exceptions import PipeRunError
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.errors.problem import ProblemView
from pipelex.graph.node_problem import NODE_PROBLEM_FAULT_MESSAGE, make_node_problem
from pipelex.pipe_run.exceptions import PipeRouterError
from pipelex.pipe_run.located_failure import reported_failure_code
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.helpers.recovered_problem import make_recovered_function_raised


class TestNodeProblem:
    @pytest.mark.builds_problems_without_required_params(
        reason="builds the step's failure with a message alone, to check where its problem is located"
    )
    def test_a_pipelex_error_records_its_problem_located_at_the_node(self) -> None:
        error = StuffFactoryError("Error combining stuffs for concept Report").with_error_code(CoreCode.PIPE_OUTPUT_INVALID)

        problem = make_node_problem(error=error, pipe_code="analyze", pipe_path=["flow", "analyze"])

        assert problem.code == CoreCode.PIPE_OUTPUT_INVALID
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "analyze", "path": ["flow", "analyze"]}
        assert problem.params is not None
        assert problem.params.as_wire()["pipe"] == "analyze"

    @pytest.mark.builds_problems_without_required_params(reason="builds the step's failure with a message alone, to check the view its node records")
    def test_the_node_records_the_caller_view(self) -> None:
        """The graph is read by whoever reads the run: no diagnostics, and never the error's own message."""
        error = StuffFactoryError("a deployment's validator said: secret-ish text")

        problem = make_node_problem(error=error, pipe_code="analyze", pipe_path=["flow", "analyze"])

        assert problem.diagnostics is None
        assert "secret-ish text" not in str(problem.to_wire())

    @pytest.mark.builds_problems_without_required_params(
        reason="builds the step's failure with a message alone, to check where its problem is located"
    )
    def test_an_entry_pipe_names_itself_as_its_path(self) -> None:
        problem = make_node_problem(error=StuffFactoryError("refused"), pipe_code="flow", pipe_path=[])

        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "flow", "path": ["flow"]}

    def test_a_wrapper_above_a_recovered_problem_records_that_problem(self) -> None:
        """A step's `PipeRunError` above a carrier of a recovered problem records the carried code, not the carrier's class code."""
        carrier = make_recovered_function_raised(pipe="explode", function="funcs.explode.explode", message="secret-ish text the sandbox wrote")
        wrapper = PipeRunError(message="PipeFunc 'explode' failed during execution", run_mode=PipeRunMode.LIVE, pipe_code="explode")
        wrapper.__cause__ = carrier

        problem = make_node_problem(error=wrapper, pipe_code="explode", pipe_path=["flow", "explode"])

        assert carrier.own_error_code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.code == CoreCode.PIPE_FUNCTION_RAISED
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "explode", "path": ["flow", "explode"]}
        assert problem.params is not None
        assert problem.params.as_wire() == {"pipe": "explode", "function": "funcs.explode.explode"}
        # The caller's view: no diagnostics, and none of the carrier's or the wrapper's own text.
        assert problem.diagnostics is None
        wire = str(problem.to_wire())
        assert "secret-ish text" not in wire
        assert "failed during execution" not in wire

    def test_a_wrapper_records_the_code_the_run_fails_with(self) -> None:
        """The node and the run read one answer: the node's problem has the code of the run's located failure."""
        carrier = make_recovered_function_raised(pipe="explode", function="funcs.explode.explode")
        wrapper = PipeRunError(message="PipeFunc 'explode' failed during execution", run_mode=PipeRunMode.LIVE, pipe_code="explode")
        wrapper.__cause__ = carrier
        located = PipeRouterError.make_located(
            failure=wrapper, run_mode=PipeRunMode.LIVE, pipe_code="explode", output_name=None, pipe_stack=["flow", "explode"]
        )
        located.__cause__ = wrapper

        node_problem = make_node_problem(error=wrapper, pipe_code="explode", pipe_path=["flow", "explode"])
        run_problem = located.to_problem(view=ProblemView.CALLER)

        assert node_problem.to_wire() == run_problem.to_wire()

    def test_an_error_implying_its_code_records_that_code(self) -> None:
        """An inference error implying its category's code, above a cause that carries none, records the implied code.

        The error carries no code of its own, so a walk below it alone would stop at its cause's fallback,
        `runtime.unexpected`, while the run reports the code the error implies: the node reads that code too.
        """
        cause = PipeRunError(message="the inner step failed", run_mode=PipeRunMode.LIVE, pipe_code="inner")
        error = LLMCompletionError(message="the completion failed", error_category=InferenceErrorCategory.TRANSIENT)
        error.fill_model_and_provider("gpt-4o-mini", backend_name="openai")
        error.__cause__ = cause

        problem = make_node_problem(error=error, pipe_code="summarize", pipe_path=["flow", "summarize"])

        assert error.own_error_code is None
        assert error.implied_error_code == CoreCode.PROVIDER_UNAVAILABLE
        assert reported_failure_code(failure=error) == CoreCode.PROVIDER_UNAVAILABLE
        assert problem.code == CoreCode.PROVIDER_UNAVAILABLE
        assert problem.location is not None
        assert problem.location.as_wire() == {"pipe": "summarize", "path": ["flow", "summarize"]}

    def test_a_foreign_exception_is_a_fault_of_ours(self) -> None:
        problem = make_node_problem(error=RuntimeError("The worker was lost"), pipe_code="flow", pipe_path=["flow"])

        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert "The worker was lost" not in str(problem.to_wire())

    def test_a_problem_that_cannot_be_built_records_a_fault_of_ours(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """Tracing never changes how a run fails: a problem that raises is logged, and the node records `runtime.unexpected`."""
        error = StuffFactoryError("Input 'topic' is missing")
        mocker.patch.object(error, "to_problem", side_effect=RuntimeError("The problem could not be built"))

        with caplog.at_level(logging.ERROR):
            problem = make_node_problem(error=error, pipe_code="flow", pipe_path=["flow"])

        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        (record,) = [record for record in caplog.records if record.getMessage().endswith(NODE_PROBLEM_FAULT_MESSAGE)]
        assert record.levelno == logging.ERROR
        assert (vars(record)["failed_error_type"], vars(record)["error.type"]) == ("StuffFactoryError", "RuntimeError")
