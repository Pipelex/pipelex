from collections.abc import Sequence
from typing import Any, cast

from pydantic import ValidationError
from temporalio import activity
from temporalio.exceptions import ApplicationError

from pipelex.base_exceptions import ErrorReport, PipelexError
from pipelex.cogt.exceptions import find_inference_error_category_in_chain
from pipelex.config import get_config
from pipelex.temporal.exceptions import UnrecoverableWorkflowFailureError
from pipelex.temporal.log_temporal import activity_log, workflow_log
from pipelex.types import Self


def error_report_dict_from_details(details: Sequence[Any]) -> dict[str, Any] | None:
    """Recover the ``ErrorReport`` dict packed into ``ApplicationError.details``.

    The bridge packs ``exc.to_error_report().to_dict()`` as the first details
    entry. After Temporal serialization the dict comes back as a plain mapping;
    we identify it by its ``error_type`` / ``message`` shape so an unrelated
    details payload is not mistaken for an error report.
    """
    for entry in details:
        if isinstance(entry, dict) and "error_type" in entry and "message" in entry:
            return cast("dict[str, Any]", entry)
    return None


def _find_error_report_dict(exc: BaseException) -> dict[str, Any] | None:
    """Return the first details-packed ``ErrorReport`` dict in the ``__cause__`` chain of ``exc``.

    Temporal sets ``__cause__`` on the ``WorkflowFailureError`` raised by
    ``client.execute_workflow`` to the deserialized failure; the structured
    ``ErrorReport`` packed by the activity bridge rides on an
    ``ApplicationError``'s ``details``. A workflow that wraps a failed child
    workflow re-raises its own failure — Temporal serializes that re-raised
    ``WorkflowExecutionError`` as an outer ``ApplicationError`` whose ``details``
    are empty, with the report-carrying child ``ApplicationError`` deeper in the
    chain. The walk therefore continues past a report-less ``ApplicationError``
    rather than stopping at the first one. The child-workflow boundary exposes
    its failure via ``ChildWorkflowError.cause`` rather than ``__cause__``, so
    its caller passes ``exc.cause`` straight in.
    """
    node: BaseException | None = exc
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        if isinstance(node, ApplicationError):
            report_dict = error_report_dict_from_details(node.details)
            if report_dict is not None:
                return report_dict
        seen.add(id(node))
        node = node.__cause__
    return None


def _message_from_exc(exc: BaseException) -> str:
    """Return the most informative message available from a Temporal failure chain.

    ``WorkflowFailureError`` carries the generic outer text ``"Workflow execution failed"``;
    the underlying ``__cause__`` (a Temporal ``ApplicationError`` carrying the
    worker exception, or a non-Temporal exception) holds the real detail. We walk
    the ``__cause__`` chain and surface the deepest non-empty message, falling
    back to ``repr(exc)`` when every message in the chain is unset.
    """
    deepest_message = ""
    node: BaseException | None = exc
    seen: set[int] = set()
    while node is not None and id(node) not in seen:
        seen.add(id(node))
        text = str(node)
        if text:
            deepest_message = text
        node = node.__cause__
    return deepest_message or repr(exc)


def recover_error_report(exc: BaseException) -> ErrorReport:
    """Recover the structured ``ErrorReport`` from a Temporal failure.

    Walks the ``__cause__`` chain for an ``ApplicationError`` carrying a
    details-packed report (see :func:`error_report_dict_from_details`) and
    rebuilds an :class:`ErrorReport` from it. When no such payload is present
    in the chain — a non-Pipelex exception, a worker crash, a heartbeat
    timeout, or anything else that crossed the boundary without going through
    the activity bridge — synthesizes an :class:`UnrecoverableWorkflowFailureError`
    report so callers in the error-recovery path always have a structured
    report to surface. The synthesized report carries the most informative
    message recoverable from the failure chain (see :func:`_message_from_exc`)
    and a stable identity / classification
    (``error_type="UnrecoverableWorkflowFailureError"``,
    ``error_domain=RUNTIME``).

    A report dict that is found but fails :meth:`ErrorReport.from_dict`
    validation is an internal contract violation within one deploy — the
    activity bridge and the submitter share the schema. Raising there would
    abort the caller before it can deliver the failure webhook, leaving the
    receiver with no notification at all, so this synthesizes the same
    :class:`UnrecoverableWorkflowFailureError` fallback — carrying the
    recovered ``message`` and an ``[error report failed schema validation]``
    marker. The failed run is still reported to the receiver and the contract
    bug stays visible: a bug to fix, but not at the cost of a silent run.
    """
    report_dict = _find_error_report_dict(exc)
    if report_dict is not None:
        try:
            return ErrorReport.from_dict(report_dict)
        except ValidationError:
            # The details payload looked like a report — it carried error_type
            # and message — but failed the ErrorReport schema. Synthesize the
            # fallback instead of raising, so the caller still delivers the
            # failure webhook; the recovered message plus marker keep the
            # contract bug visible on the wire.
            recovered_message = report_dict.get("message") or _message_from_exc(exc)
            fallback_message = f"{recovered_message} [error report failed schema validation]"
            return UnrecoverableWorkflowFailureError(fallback_message).to_error_report()
    return UnrecoverableWorkflowFailureError(_message_from_exc(exc)).to_error_report()


class TemporalError(ApplicationError):
    """A Pipelex error crossing the Temporal activity → workflow boundary.

    Two things travel with the error across the boundary:

    - ``non_retryable``: when the exception's ``__cause__`` chain carries a
      ``CogtError`` with an ``InferenceErrorCategory`` the flag is derived from
      ``category.is_retryable`` — recovered even under the ``PipeRunError`` /
      ``PipeRouterError`` / ``PipelineExecutionError`` wrappers, by walking the
      ``__cause__`` chain. For a chain carrying no category the bridge falls
      back to the configured ``non_retryable_error_types`` class-name list.
    - ``error_report``: the structured ``ErrorReport`` dict is packed into
      ``ApplicationError.details`` so workflow code keeps ``error_category``,
      ``user_action``, ``model`` and ``provider`` — not just the message string.
    """

    def __init__(
        self,
        message: str,
        error_type: str | None,
        non_retryable: bool = False,
        error_report: dict[str, Any] | None = None,
    ):
        details: tuple[dict[str, Any], ...] = (error_report,) if error_report is not None else ()
        super().__init__(
            message,
            *details,
            type=error_type,
            non_retryable=non_retryable,
        )
        self.error_report = error_report

    @classmethod
    def _log_critical(cls, message: str) -> None:
        """Log a non-retryable error at critical severity, in the active Temporal context.

        ``from_message_exception`` runs activity-side and ``from_app_error``
        workflow-side; ``workflow.logger`` raises ``_NotInWorkflowEventLoopError``
        outside a workflow event loop, so the logger must match the context.
        """
        if activity.in_activity():
            activity_log.critical(message)
        else:
            workflow_log.critical(message)

    @classmethod
    def _log_error(cls, message: str) -> None:
        """Log a retryable error at error severity, in the active Temporal context.

        See ``_log_critical`` for why the logger must match the Temporal context.
        """
        if activity.in_activity():
            activity_log.error(message)
        else:
            workflow_log.error(message)

    @classmethod
    def _error_type_in_name_list(cls, error_type: str | None) -> bool:
        """Check ``error_type`` against the configured ``non_retryable_error_types`` list.

        The fallback retry signal for exceptions that carry no
        ``InferenceErrorCategory`` — see ``RetryPolicyConfig.non_retryable_error_types``.
        """
        temporal_config = get_config().temporal
        all_non_retryable = temporal_config.worker_config.all_non_retryable_error_types(
            queue_options_by_queue=temporal_config.queue_options,
        )
        return error_type in all_non_retryable

    @classmethod
    def from_app_error(cls, exc: ApplicationError) -> Self:
        """Re-wrap an ``ApplicationError`` observed in workflow code.

        The incoming error has already crossed Temporal serialization, so its
        ``non_retryable`` flag and details payload reflect the decision the
        activity-side bridge made. We preserve both. Only when neither is
        present (a plain ``ApplicationError`` that never went through this
        bridge) do we fall back to the class-name list for the severity decision.
        """
        message = exc.message
        error_type = exc.type
        error_report = error_report_dict_from_details(exc.details)
        non_retryable = exc.non_retryable
        if not non_retryable and error_report is None:
            non_retryable = cls._error_type_in_name_list(error_type)
        if non_retryable:
            cls._log_critical(f"Non retryable error from ApplicationError[{error_type}]: {message}")
        else:
            cls._log_error(f"Error from ApplicationError[{error_type}]: {message}")
        return cls(
            message=message,
            error_type=error_type,
            non_retryable=non_retryable,
            error_report=error_report,
        )

    @classmethod
    def from_message_exception(cls, exc: PipelexError) -> Self:
        """Convert a Pipelex exception raised inside an activity into a ``TemporalError``.

        When the exception's ``__cause__`` chain carries a ``CogtError`` with an
        ``InferenceErrorCategory``, retryability flows from ``category.is_retryable``
        — recovered even when wrapper exceptions (``PipeRunError``, ``PipeRouterError``,
        ``PipelineExecutionError``) sit on top. A chain with no categorized ``CogtError``
        falls back to the configured ``non_retryable_error_types`` class-name list.
        """
        message = exc.message
        error_type = exc.__class__.__name__
        error_report = exc.to_error_report().to_dict()
        non_retryable = cls._is_non_retryable(exc=exc, error_type=error_type)
        if non_retryable:
            cls._log_critical(f"Non retryable error from PipelexError[{error_type}]: {message}")
        else:
            cls._log_error(f"Retryable error from PipelexError[{error_type}]: {message}")
        return cls(
            message=message,
            error_type=error_type,
            non_retryable=non_retryable,
            error_report=error_report,
        )

    @classmethod
    def _is_non_retryable(cls, exc: PipelexError, error_type: str) -> bool:
        """Decide retryability — category-aware for ``CogtError``, name-list fallback otherwise.

        A categorized ``CogtError`` is usually wrapped — ``PipeRunError`` ->
        ``PipeRouterError`` -> ``PipelineExecutionError`` — by the time it reaches the
        activity boundary, so the ``InferenceErrorCategory`` is recovered by walking the
        ``__cause__`` chain rather than inspecting only the outer exception. This keeps
        ``non_retryable`` consistent with the chain-enriched ``retryable`` field of the
        ``ErrorReport`` packed alongside it. A chain carrying no category falls back to
        the configured ``non_retryable_error_types`` class-name list.
        """
        error_category = find_inference_error_category_in_chain(exc)
        if error_category is not None:
            return not error_category.is_retryable
        return cls._error_type_in_name_list(error_type)
