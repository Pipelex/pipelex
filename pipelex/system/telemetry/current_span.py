"""Making a span the current one while the work it measures runs.

The runtime starts its spans with an explicit parent carried in the job metadata, because a run's trace
is derived from its business identifiers and has to survive a process boundary, where OpenTelemetry's
current context does not travel. A span started that way is not current, so nothing that reads the
current context sees it: the log sinks writing a record's trace context, a library's own
instrumentation opening a child span, an error tracker attaching an event to its trace. Entering this
context manager around the work makes the span current for its duration, in this task only, and
restores the previous context on the way out. It never ends the span, records an exception on it or
sets its status, which stay with the code that started it, and it never becomes the way a parent
reaches a child: the job metadata still carries that, so a child running in another process gets the
same parent it always did.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from opentelemetry import trace

if TYPE_CHECKING:
    from collections.abc import Generator

    from opentelemetry.trace import Span


@contextmanager
def span_made_current(*, span: Span | None) -> Generator[None]:
    """Make ``span`` current while the block runs; a ``None`` span, no tracer or a dry run, leaves the context alone."""
    if span is None:
        yield
        return
    with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
        yield
