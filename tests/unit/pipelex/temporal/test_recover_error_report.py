"""Unit tests for ``recover_error_report`` — submitter-side report recovery.

When a Temporal workflow fails, the structured ``ErrorReport`` rides on the
deserialized ``ApplicationError.details``. ``recover_error_report`` walks the
``__cause__`` chain, finds that ``ApplicationError``, and rebuilds the report —
tolerating worker/submitter version skew and never crashing the error path.
"""

from typing import Any

from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError

from pipelex.base_exceptions import ErrorDomain, ErrorReport
from pipelex.cogt.inference.error_classification import UserAction, UserActionKind
from pipelex.temporal.tprl.temporal_error import recover_error_report

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


def _app_error(*details: Any) -> ApplicationError:
    """Build an ``ApplicationError`` as the activity bridge would — report dict in ``details``."""
    return ApplicationError("rate limited on the worker", *details, type="CogtError")


def _workflow_failure(cause: BaseException) -> WorkflowFailureError:
    """Wrap ``cause`` in a ``WorkflowFailureError`` — what ``client.execute_workflow`` raises."""
    return WorkflowFailureError(cause=cause)


class TestRecoverErrorReport:
    def test_recovers_full_report_from_application_error_in_chain(self) -> None:
        """The packed report is rebuilt with every classification field intact."""
        failure = _workflow_failure(_app_error(_FULL_REPORT.to_dict()))
        assert recover_error_report(failure) == _FULL_REPORT

    def test_g2_unknown_key_dropped_for_version_skew(self) -> None:
        """G2 — a report dict from a newer worker (extra field) is accepted; the unknown key is dropped."""
        skewed = {**_FULL_REPORT.to_dict(), "future_field": "added by a newer Pipelex worker"}
        failure = _workflow_failure(_app_error(skewed))
        assert recover_error_report(failure) == _FULL_REPORT

    def test_g3_malformed_details_recovers_nothing(self) -> None:
        """G3 — a details dict that fails ``ErrorReport`` validation yields ``None`` (no crash)."""
        # It has the error_type/message shape so it is picked up as a report,
        # but ``retryable`` is the wrong type → from_dict raises, caught internally.
        malformed = {"error_type": "X", "message": "m", "retryable": ["not", "a", "bool"]}
        failure = _workflow_failure(_app_error(malformed))
        assert recover_error_report(failure) is None

    def test_g4_application_error_without_report_details_recovers_nothing(self) -> None:
        """G4 — an ``ApplicationError`` carrying no report payload yields ``None``."""
        failure = _workflow_failure(_app_error())
        assert recover_error_report(failure) is None

    def test_no_application_error_in_chain_recovers_nothing(self) -> None:
        """A failure with no ``ApplicationError`` in its ``__cause__`` chain yields ``None``."""
        failure = _workflow_failure(RuntimeError("plain non-Temporal failure"))
        assert recover_error_report(failure) is None
