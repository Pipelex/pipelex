import logging

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.graph.node_problem import NODE_PROBLEM_FAULT_MESSAGE, make_node_problem


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
