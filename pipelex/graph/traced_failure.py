"""What the execution graph records of the error that ended a node: its message, and whether it was written for the caller."""

from typing import NamedTuple

from pipelex.base_exceptions import PipelexError


class TracedFailure(NamedTuple):
    """The message a failed node records, and whether that message was written for the caller."""

    message: str
    caller_facing: bool


def make_traced_failure(*, error: BaseException) -> TracedFailure:
    """What a node ended by `error` records of it.

    Whether the message was written for the caller is the error report's to say, as it says it of the run's own failure:
    a Pipelex error records its report's message and `caller_facing_message`, and any other exception records its text,
    which is never written for the caller.
    """
    if isinstance(error, PipelexError):
        error_report = error.to_error_report()
        return TracedFailure(message=error_report.message, caller_facing=error_report.caller_facing_message)
    return TracedFailure(message=str(error), caller_facing=False)
