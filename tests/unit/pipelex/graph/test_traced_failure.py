import logging

import pytest
from pipelex.graph.traced_failure import ERROR_REPORT_FAULT_MESSAGE, TracedFailure, make_traced_failure
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexError
from pipelex.core.stuffs.exceptions import StuffFactoryError


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

    def test_a_report_that_cannot_be_built_records_the_errors_text(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """Tracing never changes how a run fails: a report that raises is logged, and the node records the error's text."""
        error = StuffFactoryError("Input 'topic' is missing").as_caller_fault()
        mocker.patch.object(error, "to_error_report", side_effect=RuntimeError("The report could not be built"))

        with caplog.at_level(logging.ERROR):
            traced_failure = make_traced_failure(error=error)

        assert traced_failure == TracedFailure(message=str(error), caller_facing=False)
        (record,) = [record for record in caplog.records if record.getMessage().endswith(ERROR_REPORT_FAULT_MESSAGE)]
        assert record.levelno == logging.ERROR
        assert (vars(record)["failed_error_type"], vars(record)["error.type"]) == ("StuffFactoryError", "RuntimeError")
