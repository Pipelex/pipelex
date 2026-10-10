"""The fields every summary event shares, the event a unit of work ends with: how long it took, what it cost and how it ended.

A summary event, the one an inference call ends with or the one a pipe run ends with, says how long the work took in
``duration_ms``, and how it ended in ``outcome``: ``success`` when it returned, ``error`` when it raised, naming the
class of the exception in ``error.type``, the OpenTelemetry semantic-convention key for the class of error an operation
ended with, and ``cancelled`` when it was stopped from outside rather than failing, by a cancellation, an interrupt or
the interpreter exiting. A query counts failures by ``outcome`` and groups them by ``error.type`` without parsing any
text, and the siblings a failure in a batch cancels are not counted as failures of their own. The
exception's own text stays off the event: the exception propagates to whoever handles it, which logs it there with its
traceback. An inference call's event also says what the call cost, in ``cost_usd``.

The names live here, beside the console layouts that draw the events, so a layout reads them without importing the
code that logs them, ``SummaryEvent`` (``pipelex.tools.log.summary_event``) among it.
"""

from enum import StrEnum
from time import perf_counter

from pipelex.tools.log.error_fields import ERROR_TYPE_FIELD

#: How the unit of work ended.
OUTCOME_FIELD = "outcome"

#: How long the unit of work took, in milliseconds, as a number.
DURATION_MS_FIELD = "duration_ms"

#: What an inference call cost, in US dollars, as a number.
COST_USD_FIELD = "cost_usd"

#: The summary event a line is about, by its message.
SUMMARY_EVENT_FIELD = "summary_event"


class Outcome(StrEnum):
    """The values of ``outcome``."""

    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


def outcome_fields(*, error: BaseException | None) -> dict[str, str]:
    """The ``outcome`` field of a unit of work, and its ``error.type`` when it failed.

    An exception that is not an ``Exception`` is not a failure of the work: Python keeps that branch of the hierarchy
    for what stops work from outside, a task cancelled (``asyncio.CancelledError``), as a batch or a parallel
    controller cancels its siblings and a client cancels a run, an interrupt (``KeyboardInterrupt``), a generator
    closed (``GeneratorExit``) or the interpreter exiting (``SystemExit``). That work was cancelled, and its event
    names no ``error.type``.

    Args:
        error: The exception the work ended with, or ``None`` when it returned.

    Returns:
        ``{"outcome": "success"}``, ``{"outcome": "cancelled"}``, or
        ``{"outcome": "error", "error.type": <the exception's class name>}``.
    """
    if error is None:
        return {OUTCOME_FIELD: Outcome.SUCCESS}
    if not isinstance(error, Exception):
        return {OUTCOME_FIELD: Outcome.CANCELLED}
    return {OUTCOME_FIELD: Outcome.ERROR, ERROR_TYPE_FIELD: type(error).__name__}


def start_clock() -> float:
    """A reading of the monotonic clock a summary event's duration is measured from, for ``elapsed_ms``."""
    return perf_counter()


def elapsed_ms(*, started_at: float) -> float:
    """The milliseconds since ``started_at``, a ``start_clock`` reading, to the microsecond."""
    return round((perf_counter() - started_at) * 1000, 3)
