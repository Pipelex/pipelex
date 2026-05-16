from collections.abc import Sequence
from typing import Any, cast

from temporalio import activity
from temporalio.exceptions import ApplicationError

from pipelex.base_exceptions import PipelexError
from pipelex.cogt.exceptions import CogtError
from pipelex.config import get_config
from pipelex.temporal.log_temporal import activity_log, workflow_log
from pipelex.types import Self


def _error_report_from_details(details: Sequence[Any]) -> dict[str, Any] | None:
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


class TemporalError(ApplicationError):
    """A Pipelex error crossing the Temporal activity → workflow boundary.

    Two things travel with the error across the boundary:

    - ``non_retryable``: for a ``CogtError`` carrying an ``InferenceErrorCategory``
      the flag is derived from ``category.is_retryable`` — the same signal the
      in-process ``PipeRouter`` retry loop consults. For category-less
      exceptions the bridge falls back to the configured
      ``non_retryable_error_types`` class-name list.
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
        error_report = _error_report_from_details(exc.details)
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

        For a ``CogtError`` carrying an ``InferenceErrorCategory``, retryability
        flows from ``category.is_retryable``. For a category-less exception
        (non-``CogtError`` ``PipelexError``, or a ``CogtError`` raised without a
        category) it falls back to the configured ``non_retryable_error_types``
        class-name list.
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
        """Decide retryability — category-aware for ``CogtError``, name-list fallback otherwise."""
        if isinstance(exc, CogtError) and exc.error_category is not None:
            return not exc.error_category.is_retryable
        return cls._error_type_in_name_list(error_type)
