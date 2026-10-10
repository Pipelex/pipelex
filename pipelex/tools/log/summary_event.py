"""The timed context manager a unit of work ends with its summary event through, once, however it ends.

``SummaryEvent`` is what the event an inference call ends with and the event a pipe run ends with share: it starts the
clock when the work starts, logs the event once when the work ends, its outcome read off the exception leaving the
block, and never lets a failure of the event's own change the work's outcome. The fields it writes are named in
``pipelex.tools.log.summary_fields``, which the console layouts read without importing this module and the logger it
logs through.
"""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Self

from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log import log
from pipelex.tools.log.summary_fields import DURATION_MS_FIELD, SUMMARY_EVENT_FIELD, elapsed_ms, outcome_fields, start_clock

if TYPE_CHECKING:
    from types import TracebackType

#: The message of the warning a summary event that could not be logged is replaced with.
SUMMARY_EVENT_FAILED_MESSAGE = "A summary event could not be logged"


class SummaryEvent(ABC):
    """Times a unit of work and logs the one event it ends with, once, when it ends, however it ends.

    A context manager around the work. Entering it starts the clock, and leaving it logs the event: the work's own
    fields, then ``duration_ms``, then ``outcome``, read off the exception leaving the block, with ``error.type`` on
    failure, and ``cancelled`` for work stopped from outside. It never handles that exception, which goes on as it came.

    The event is the work's measurement, never part of its result: if its fields cannot be built or logged, a call
    that succeeded must still succeed and one that failed must fail with its own exception. So a failure of the
    event's own is logged once in its place, as a warning, and the work's outcome goes on unchanged; a warning the
    handlers refuse in their turn is dropped, since nothing is left to say it with.

    Some work runs under a context that only exists part of the way, a span that is started after checks that may
    refuse the work. ``ends_here`` enters the event again for the inner block, so the event is logged when that block
    ends, still under the context the block sets, while a refusal before it still ends the work with its event, logged
    when the outer block ends. The clock starts at the first entry, and the event is logged at the first exit, so
    nothing that can fail may follow the inner block inside the outer one.

    A subclass gives the work's fields in ``_work_fields`` and logs the event in ``_log_event``, from its own module,
    with its fixed message and its console layout, so the event is on the logger of the code it measures and a host
    quietens one event without the other.

    Args:
        message: The event's message, which names it in the warning a failure of its own is replaced with.
    """

    _started_at: float

    def __init__(self, *, message: str) -> None:
        self._message = message
        self._has_started = False
        self._has_ended = False

    def __enter__(self) -> Self:
        if not self._has_started:
            self._has_started = True
            self._started_at = start_clock()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> None:
        if self._has_ended:
            return
        self._has_ended = True
        self._end(error=exc_value)

    def ends_here(self) -> Self:
        """The event again, to enter around the inner block whose end it is logged at.

        ``with pipelex_span_active(span=span), call_summary.ends_here():`` logs the event while the span is still the
        active Pipelex span, so the line names it, even where the block has already ended the span itself, and the
        outer ``with call_summary:`` logs it only when the inner block was never reached.
        """
        return self

    @abstractmethod
    def _work_fields(self) -> dict[str, Any]:
        """The fields that say what the work was, read when it ends, before its duration and its outcome."""

    @abstractmethod
    def _log_event(self, *, fields: dict[str, Any]) -> None:
        """Log the event with ``fields``, at INFO, under its fixed message and its console layout."""

    def _end(self, *, error: BaseException | None) -> None:
        """Log the event the work ends with, having raised ``error`` or not, or the warning a failure of its own is logged as.

        Nothing raised here leaves it, the warning's own failure included, so the work's result or exception goes on as it came.
        """
        try:
            duration_ms = elapsed_ms(started_at=self._started_at)
            fields = {**self._work_fields(), DURATION_MS_FIELD: duration_ms, **outcome_fields(error=error)}
            self._log_event(fields=fields)
        except Exception as event_error:  # ruff: ignore[blind-except]
            # (2) the work's fields are read from whatever the work recorded, a provider worker's usage included, a plugin's
            # among them, and the event goes through whatever handlers the host installed, so what building and logging it can
            # raise cannot be enumerated, and the work's outcome must not change.
            # (2) the warning goes through the same handlers, which may refuse it as they refused the event; then there is
            # nowhere left to say so, and the work's outcome still must not change.
            with contextlib.suppress(Exception):
                log.warning(SUMMARY_EVENT_FAILED_MESSAGE, fields={SUMMARY_EVENT_FIELD: self._message, **error_fields(exc=event_error)})
