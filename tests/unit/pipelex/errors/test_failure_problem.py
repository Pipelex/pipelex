from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from mthds.protocol.problem.registry import CoreCode
from pydantic import BaseModel, ValidationError

from pipelex.base_exceptions import PipelexError
from pipelex.errors.failure_problem import failure_log_fields, failure_problem, format_problem_location, format_problem_verdict
from pipelex.errors.problem import ProblemView, make_location
from pipelex.migration.exceptions import FormerReleaseConfigError

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

    def test_the_log_fields_name_the_code_and_the_chain_s_classes_and_no_text(self) -> None:
        """No chained exception's text reaches the fields, the foreign ``ValidationError``'s included."""
        failure = _chained_failure()

        fields = failure_log_fields(error=failure, problem=failure_problem(error=failure))

        assert fields == {"error.code": "runtime.unexpected", "error.type": "ValueError", "error.chain": ["ValueError", "ValidationError"]}
        assert _PLANTED_RUN_DATA not in repr(fields)

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
