from typing import Any

import pytest
from mthds.protocol.problem.registry import CoreCode
from typing_extensions import override

from pipelex.base_exceptions import PipelexError
from pipelex.errors.problem import ProblemView, make_location, make_problem
from pipelex.system.error_tracking.error_report import ErrorReportKind, make_error_report
from pipelex.system.exceptions import ToolError

_PLANTED_INPUT = "patient record 123-45-6789"


class _HookFaultError(PipelexError):
    """A Pipelex error whose problem cannot be built, as a faulty override in a plugin's error could."""

    error_code = CoreCode.INPUT_INVALID

    @override
    def problem_params(self) -> dict[str, Any]:
        msg = "the parameters could not be read"
        raise RuntimeError(msg)


def _fail_with_a_planted_input(*, document: str) -> None:
    """Raise from a frame whose locals hold a run's input, as a pipe's code would."""
    if document:
        msg = "the document could not be read"
        raise ValueError(msg)


def _caught_planted_failure() -> ValueError:
    try:
        _fail_with_a_planted_input(document=_PLANTED_INPUT)
    except ValueError as exc:
        return exc
    msg = "the planted failure did not raise"
    raise AssertionError(msg)


class TestErrorReport:
    def test_an_exception_is_grouped_by_its_code_and_where_it_was_raised(self) -> None:
        error = _caught_planted_failure()

        report = make_error_report(
            kind=ErrorReportKind.RUN_FAILURE, exception=error, pipeline_run_id="plr-1", request_id="req-1", pipe_code="summarize"
        )

        assert report.code == CoreCode.RUNTIME_UNEXPECTED
        assert report.raise_site == f"{__name__}:_fail_with_a_planted_input"
        assert report.fingerprint == [CoreCode.RUNTIME_UNEXPECTED, f"{__name__}:_fail_with_a_planted_input"]
        assert report.error_type == "ValueError"
        assert report.error_chain == ["ValueError"]
        assert report.frames[-1].endswith("in _fail_with_a_planted_input")
        assert report.tags == {
            "error.code": CoreCode.RUNTIME_UNEXPECTED,
            "error.domain": "runtime",
            "error.report_kind": "run_failure",
            "error.type": "ValueError",
            "error.raise_site": f"{__name__}:_fail_with_a_planted_input",
            "pipe_code": "summarize",
            "pipeline_run_id": "plr-1",
            "request_id": "req-1",
        }

    def test_the_identifiers_never_carry_a_run_input_held_in_the_failing_frame(self) -> None:
        report = make_error_report(kind=ErrorReportKind.UNCAUGHT, exception=_caught_planted_failure())

        for value in (repr(report.tags), repr(report.fields), repr(report.frames), repr(report.fingerprint)):
            assert _PLANTED_INPUT not in value

    def test_a_pipelex_error_is_reported_in_the_operator_view_of_its_own_problem(self) -> None:
        error = ToolError("the tool failed")

        report = make_error_report(kind=ErrorReportKind.HANDLED, exception=error, pipeline_run_id="plr-2")

        assert report.problem.diagnostics is not None
        assert report.problem.diagnostics.error_class == "ToolError"
        assert report.problem.pipeline_run_id == "plr-2"
        assert report.raise_site is None

    def test_a_problem_that_cannot_be_built_falls_back_to_the_catch_all_code(self) -> None:
        report = make_error_report(kind=ErrorReportKind.HANDLED, exception=_HookFaultError("bad"))

        assert report.code == CoreCode.RUNTIME_UNEXPECTED

    def test_the_pipe_the_problem_locates_is_the_failing_pipe(self) -> None:
        problem = make_problem(code=CoreCode.RUNTIME_UNEXPECTED, view=ProblemView.OPERATOR, location=make_location(pipe="summarize"))

        report = make_error_report(kind=ErrorReportKind.RUN_FAILURE, problem=problem, pipe_code="two_steps")

        assert report.pipe_code == "summarize"

    def test_a_report_needs_an_exception_or_a_problem(self) -> None:
        with pytest.raises(ValueError, match="needs an exception or a problem"):
            make_error_report(kind=ErrorReportKind.HANDLED)
