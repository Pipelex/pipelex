"""Unit tests for ``WorkflowExecutionError.to_error_report()``.

When the submitter recovered a structured report, ``WorkflowExecutionError``
carries it and ``to_error_report()`` returns it verbatim. With no recovered
report it falls through to the base ``__cause__``-chain enrichment.
"""

from pipelex.base_exceptions import ErrorDomain, ErrorReport, PipelexConfigError
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.temporal.exceptions import WorkflowExecutionError

_FULL_REPORT = ErrorReport(
    error_type="CogtError",
    message="rate limited on the worker",
    error_category="capacity",
    error_domain=ErrorDomain.RUNTIME,
    retryable=False,
    user_action=UserAction(kind=UserActionKind.CHECK_BILLING, detail="check your billing page"),
    model="gpt-5",
    provider="openai",
)


class TestWorkflowExecutionError:
    def test_to_error_report_returns_recovered_report_verbatim(self) -> None:
        """With a recovered report present, ``to_error_report`` returns it unchanged."""
        error = WorkflowExecutionError(_FULL_REPORT.message, error_report=_FULL_REPORT)
        assert error.to_error_report() == _FULL_REPORT

    def test_g7_to_error_report_falls_through_to_cause_enrichment_when_no_report(self) -> None:
        """G7 — with no recovered report, ``to_error_report`` uses base ``__cause__`` enrichment."""
        error = WorkflowExecutionError("Failed to execute workflow WfPipeRun")
        error.__cause__ = PipelexConfigError("bad config")

        report = error.to_error_report()

        assert report.error_type == "WorkflowExecutionError"
        assert report.message == "Failed to execute workflow WfPipeRun"
        # error_domain is inherited from the PipelexError cause.
        assert report.error_domain == ErrorDomain.CONFIG

    def test_to_error_report_is_generic_without_report_or_pipelex_cause(self) -> None:
        """No recovered report and no ``PipelexError`` cause → an unclassified generic report."""
        error = WorkflowExecutionError("Failed to execute workflow WfPipeRun")

        report = error.to_error_report()

        assert report.error_type == "WorkflowExecutionError"
        assert report.error_category is None
        assert report.error_domain is None
        assert report.retryable is None
