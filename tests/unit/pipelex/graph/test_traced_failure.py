import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.core.stuffs.exceptions import StuffFactoryError
from pipelex.graph.traced_failure import TracedFailure, make_traced_failure


class TestTracedFailure:
    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                StuffFactoryError("Input 'topic' is missing").as_caller_fault(),
                TracedFailure(message="Input 'topic' is missing", caller_facing=True),
            ),
            (
                StuffFactoryError("A factory refusal that is not the caller's"),
                TracedFailure(message="A factory refusal that is not the caller's", caller_facing=False),
            ),
            (RuntimeError("The worker was lost"), TracedFailure(message="The worker was lost", caller_facing=False)),
        ],
        ids=["caller_fault", "pipelex_error", "foreign_exception"],
    )
    def test_a_failure_records_its_message_and_whether_it_was_written_for_the_caller(self, error: BaseException, expected: TracedFailure) -> None:
        assert make_traced_failure(error=error) == expected

    def test_a_pipelex_error_records_its_report_message(self) -> None:
        error = StuffFactoryError("Error combining stuffs for concept Report").as_caller_fault()
        assert isinstance(error, PipelexError)
        assert make_traced_failure(error=error).message == error.to_error_report().message
