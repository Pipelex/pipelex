"""Unit tests for ``recover_error_report`` — submitter-side report recovery.

When a Temporal workflow fails, the structured ``ErrorReport`` rides on the
deserialized ``ApplicationError.details``. ``recover_error_report`` walks the
``__cause__`` chain, finds that ``ApplicationError``, and rebuilds the report.
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
    title="AI inference failed",
    type_uri="https://docs.pipelex.com/latest/errors/cogt-error/",
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

    def test_g4_application_error_without_report_details_synthesizes_unrecoverable(self) -> None:
        """G4 — an ``ApplicationError`` carrying no report payload synthesizes the unrecoverable report."""
        failure = _workflow_failure(_app_error())
        report = recover_error_report(failure)
        assert report.error_type == "UnrecoverableWorkflowFailureError"
        assert report.error_domain == ErrorDomain.RUNTIME
        assert "rate limited on the worker" in report.message

    def test_no_application_error_in_chain_synthesizes_unrecoverable(self) -> None:
        """A failure with no ``ApplicationError`` in its ``__cause__`` chain synthesizes the unrecoverable report."""
        failure = _workflow_failure(RuntimeError("plain non-Temporal failure"))
        report = recover_error_report(failure)
        assert report.error_type == "UnrecoverableWorkflowFailureError"
        assert report.error_domain == ErrorDomain.RUNTIME
        assert "plain non-Temporal failure" in report.message

    def test_found_but_invalid_report_dict_synthesizes_unrecoverable(self) -> None:
        """A report dict found in the chain but failing ``ErrorReport`` validation is an
        internal contract bug. Rather than raise — which would abort the caller before it
        can deliver the failure webhook, leaving the receiver with no notification at all —
        it synthesizes the ``UnrecoverableWorkflowFailureError`` fallback, carrying the
        recovered ``message`` and a marker flagging the validation failure. The payload
        carries every required key (``error_type``, ``message``, ``title``, ``type_uri``)
        so ``_find_error_report_dict`` picks it up, but its extra key violates
        ``ErrorReport``'s ``extra="forbid"`` and fails ``from_dict`` validation.
        """
        invalid_report_dict: dict[str, Any] = {
            "error_type": "CogtError",
            "message": "rate limited",
            "title": "AI inference failed",
            "type_uri": "https://docs.pipelex.com/latest/errors/cogt-error/",
            "future_field_we_do_not_know_about": "unexpected",
        }
        failure = _workflow_failure(_app_error(invalid_report_dict))
        report = recover_error_report(failure)
        assert report.error_type == "UnrecoverableWorkflowFailureError"
        assert report.error_domain == ErrorDomain.RUNTIME
        assert "rate limited" in report.message
        assert "schema validation" in report.message

    def test_invalid_report_with_empty_message_falls_back_to_exc_chain(self) -> None:
        """An invalid report dict with an empty ``message`` field falls back to the
        exception chain for the recovered message preamble — the ``or`` at
        ``temporal_error.py:118`` falls through when the report dict's ``message``
        is empty or whitespace. A regression swapping ``or`` to ``??`` / ``is None``
        would silently emit ``[error report failed schema validation]`` with no
        preamble at all, hiding the underlying failure text from the wire payload.
        """
        invalid_report_dict: dict[str, Any] = {
            "error_type": "CogtError",
            "message": "",  # empty: ``or`` must fall through to _message_from_exc(exc)
            "title": "AI inference failed",
            "type_uri": "https://docs.pipelex.com/latest/errors/cogt-error/",
            "future_field_we_do_not_know_about": "unexpected",
        }
        failure = _workflow_failure(_app_error(invalid_report_dict))
        report = recover_error_report(failure)
        assert report.error_type == "UnrecoverableWorkflowFailureError"
        # The fallback message must include both the ApplicationError text
        # (recovered via the exception-chain walk) and the schema-validation marker.
        assert "rate limited on the worker" in report.message
        assert "schema validation" in report.message

    def test_recovers_report_past_report_less_wrapper_application_error(self) -> None:
        """A report-less wrapper ``ApplicationError`` (e.g. a ``WorkflowExecutionError`` raised
        when a workflow wraps a failed child workflow) does not hide the report-carrying
        ``ApplicationError`` deeper in the ``__cause__`` chain.
        """
        inner = _app_error(_FULL_REPORT.to_dict())
        wrapper = ApplicationError("workflow wrapping a failed child workflow", type="WorkflowExecutionError")
        wrapper.__cause__ = inner
        failure = _workflow_failure(wrapper)
        assert recover_error_report(failure) == _FULL_REPORT
