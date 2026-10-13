"""What the execution graph records of the error that ended a node: its message, and whether it was written for the caller."""

from typing import NamedTuple

from pipelex import log
from pipelex.base_exceptions import PipelexError
from pipelex.tools.log.error_fields import error_fields

ERROR_REPORT_FAULT_MESSAGE = "The error report of a failed pipe could not be built for its trace"
"""The error logged when a failed pipe's error report raises while its node's failure is traced."""


class TracedFailure(NamedTuple):
    """The message a failed node records, and whether that message was written for the caller."""

    message: str
    caller_facing: bool


def make_traced_failure(*, error: BaseException) -> TracedFailure:
    """What a node ended by `error` records of it.

    Whether the message was written for the caller is the error report's to say, as it says it of the run's own failure:
    a Pipelex error records its report's message and `caller_facing_message`, and any other exception records its text,
    which is never written for the caller.

    Tracing never changes how a run fails. This runs while the pipe's own error is being handled, on its way to the
    caller, so building the report must not raise in its place: a report that cannot be built is logged as an error,
    and the node records the error's text, as for any other exception.
    """
    if isinstance(error, PipelexError):
        try:
            error_report = error.to_error_report()
        except Exception as report_fault:  # ruff: ignore[blind-except]
            # Unbounded code: `to_error_report` is overridden across the whole error hierarchy, the errors plugins
            # define included, and walks the error's cause chain, so what it raises cannot be enumerated. The pipe's own
            # error is the one the run fails with, so the fault is logged and the node records the error's text.
            log.error(
                ERROR_REPORT_FAULT_MESSAGE,
                fields={"failed_error_type": type(error).__name__, **error_fields(exc=report_fault)},
            )
            return TracedFailure(message=str(error), caller_facing=False)
        return TracedFailure(message=error_report.message, caller_facing=error_report.caller_facing_message)
    return TracedFailure(message=str(error), caller_facing=False)
