from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.errors.failure_problem import (
    MAX_LOGGED_FRAMES,
    failure_diagnostics,
    failure_log_fields,
    failure_problem,
    format_problem_location,
    format_problem_verdict,
)
from pipelex.errors.problem import ProblemView, make_location
from pipelex.migration.exceptions import FormerReleaseConfigError
from pipelex.tools.misc.exceptions import JsonTypeError

if TYPE_CHECKING:
    from mthds.protocol.problem.models import ProblemLocation

# A value a run carries, which an exception's text may quote and no log line may hold.
_PLANTED_RUN_DATA = "invoice-9921-iban-FR7630006000011234567890189"


class _Invoice(BaseModel):
    amount: int


def _chained_failure() -> ValueError:
    """A method function's exception quoting the run's data, raised from a foreign validation error that quotes it too."""
    try:
        _Invoice.model_validate({"amount": _PLANTED_RUN_DATA})
    except ValidationError as validation_error:
        failure = ValueError(f"could not total {_PLANTED_RUN_DATA}")
        failure.__cause__ = validation_error
        return failure
    msg = "the planted value validated"
    raise AssertionError(msg)


# A marker on the source line of a raise, which a logged frame never quotes.
_SOURCE_MARKER = "SOURCE-LINE-MARKER-5512"


def _total_of(*, value: str) -> int:
    planted_local = value
    raise KeyError(planted_local)  # SOURCE-LINE-MARKER-5512


def _raise_a_wrapped_fault(*, value: str) -> None:
    try:
        _total_of(value=value)
    except KeyError as fault:
        msg = f"the step failed on {value}"
        raise PipelexError(msg) from fault


def _recurse(*, depth: int) -> None:
    if depth == 0:
        msg = "the bottom"
        raise KeyError(msg)
    _recurse(depth=depth - 1)


class TestFailureProblem:
    def test_a_foreign_failure_is_runtime_unexpected_with_its_class_and_capped_message_in_the_diagnostics(self) -> None:
        """The operator view holds the message, capped: it is the terminal's to print, never a log line's."""
        failure = _chained_failure()

        problem = failure_problem(error=failure)

        assert problem.code == CoreCode.RUNTIME_UNEXPECTED
        assert problem.diagnostics is not None
        assert problem.diagnostics.error_class == "ValueError"
        assert problem.diagnostics.message == f"could not total {_PLANTED_RUN_DATA}"
        assert [cause.error_class for cause in problem.diagnostics.causes or []] == ["ValidationError"]

    def test_a_pipelex_failure_is_its_own_problem(self) -> None:
        failure = FormerReleaseConfigError("a former release left its gateway backend enabled")

        assert failure_problem(error=failure) == failure.to_problem(view=ProblemView.OPERATOR)

    def test_a_caught_pipelex_error_s_diagnostics_are_its_operator_view_s(self) -> None:
        failure = FormerReleaseConfigError("a former release left its gateway backend enabled")
        failure.__cause__ = KeyError("gateway")

        assert failure_diagnostics(cause=failure) == failure.to_problem(view=ProblemView.OPERATOR).diagnostics

    def test_a_caught_error_s_diagnostics_ask_nothing_of_its_code_s_parameters(self) -> None:
        """A refusal coded by the command reads the caught error's diagnostics alone, so its code's parameters go unasked.

        The JSON loader's refusal is `request.invalid`, whose `field` it cannot know; the sweep this test runs under
        fails it if reading the diagnostics built that refusal's problem.
        """
        diagnostics = failure_diagnostics(cause=JsonTypeError("the file does not hold a JSON object"))

        assert diagnostics is not None
        assert diagnostics.error_class == "JsonTypeError"

    def test_the_log_fields_name_the_code_and_the_chain_s_classes_and_no_text(self) -> None:
        """No chained exception's text reaches the fields, the foreign ``ValidationError``'s included."""
        failure = _chained_failure()

        fields = failure_log_fields(error=failure, problem=failure_problem(error=failure))

        frames = fields.pop("error.frames")
        assert fields == {"error.code": "runtime.unexpected", "error.type": "ValueError", "error.chain": ["ValueError", "ValidationError"]}
        assert all(isinstance(frame, str) for frame in frames)
        assert _PLANTED_RUN_DATA not in repr(fields)
        assert _PLANTED_RUN_DATA not in repr(frames)

    def test_the_log_fields_name_the_frames_down_to_the_fault_without_source_or_locals(self) -> None:
        """The frames go from where the failure was caught down to where its first exception was raised, by module, line and function."""
        with pytest.raises(PipelexError) as caught:
            _raise_a_wrapped_fault(value=_PLANTED_RUN_DATA)
        failure = caught.value

        frames = failure_log_fields(error=failure, problem=failure_problem(error=failure))["error.frames"]

        module = __name__
        assert frames[0].startswith(f"{module}:")
        assert frames[0].endswith(" in test_the_log_fields_name_the_frames_down_to_the_fault_without_source_or_locals")
        assert [frame.rsplit(" in ", 1)[1] for frame in frames[1:]] == ["_raise_a_wrapped_fault", "_raise_a_wrapped_fault", "_total_of"]
        assert all(frame.startswith(f"{module}:") for frame in frames)
        # No source line, whose comment carries a marker, and no local, which holds the run's data.
        assert _SOURCE_MARKER not in repr(frames)
        assert _PLANTED_RUN_DATA not in repr(frames)

    def test_the_frames_keep_the_innermost_of_a_deep_failure(self) -> None:
        with pytest.raises(KeyError) as caught:
            _recurse(depth=MAX_LOGGED_FRAMES * 2)
        failure = caught.value

        frames = failure_log_fields(error=failure, problem=failure_problem(error=failure))["error.frames"]

        assert len(frames) == MAX_LOGGED_FRAMES
        assert frames[-1].endswith(" in _recurse")

    def test_the_log_fields_of_a_pipelex_failure_carry_its_code(self) -> None:
        try:
            raise KeyError(_PLANTED_RUN_DATA)
        except KeyError as cause:
            failure = PipelexError(f"the step failed on {_PLANTED_RUN_DATA}")
            failure.__cause__ = cause

        problem = failure_problem(error=failure)
        fields = failure_log_fields(error=failure, problem=problem)

        assert fields["error.code"] == problem.code
        assert fields["error.chain"] == ["PipelexError", "KeyError"]
        assert _PLANTED_RUN_DATA not in repr(fields)

    @pytest.mark.parametrize(
        ("location", "expected"),
        [
            (None, ""),
            (make_location(pipe="summarize", path=["main", "summarize"]), "pipe 'summarize', path main > summarize"),
            (make_location(input_name="invoice", field="amount"), "input 'invoice', field 'amount'"),
            (make_location(item=2, attempt=3), "item 2, attempt 3"),
            (make_location(file="contracts.mthds", line=12, column=4), "file 'contracts.mthds', line 12, column 4"),
        ],
    )
    def test_a_location_reads_as_words(self, location: ProblemLocation | None, expected: str) -> None:
        assert format_problem_location(location=location) == expected

    def test_the_verdict_names_the_domain_and_the_retry(self) -> None:
        problem = failure_problem(error=RuntimeError("boom"))

        assert format_problem_verdict(problem=problem) == "domain runtime, retry no"
