"""The two spans a log line names: OpenTelemetry's current span, and the Pipelex span active in this task.

A line's standard trace fields name OpenTelemetry's current span in the process, which by default
Pipelex only reads and never sets, so an operator's log backend files a line under the trace of the
operator's own spans. The Pipelex span rides beside them, under the ``pipelex.trace_id`` and ``pipelex.span_id`` keys,
so a line inside a run still names the pipe or the LLM call it was logged in. The two are read
independently: a line can carry both, either, or neither.

The runtime starts its spans with an explicit parent carried in the job metadata, because a run's trace,
derived from its business identifiers or joined from the host's, has to survive a process boundary, where an in-process
context does not travel. A span started that way is current nowhere, and by default the runtime never
makes it OpenTelemetry's current span: Pipelex's tracer is its own and never the process's global one, so one of
its spans made current there would re-parent the host application's own instrumentation under a trace
only Pipelex's exporters receive, and have a sampler that follows its parent keep it. Instead, the
runtime holds the span in a context variable of its own while the work it measures runs, in this task
and in whatever copies the task's context, a thread started by ``asyncio.to_thread`` or a boot line the
holding handler replays, and restores the previous value on the way out. The log sinks read it to write
a line's ``pipelex.*`` fields, and nothing else does.

Holding a span never ends it, records an exception on it or sets its status, which stay with the code
that started it, and it never becomes the way a parent reaches a child: the job metadata still carries
that, so a child running in another process gets the same parent it always did.

An operator who declares the process's trace theirs, with ``join_host_trace``, gets the other behaviour:
a run starts under the host's current span, read here by ``host_span_to_join``, and the runtime
holds its spans with ``make_current``, so each is also OpenTelemetry's current span while the work it
measures runs, and the host's own instrumentation and an error tracker reading the current span see it.
The boot refuses that switch unless a destination of the operator's receives Pipelex's spans, so the
host's spans made children of one arrive with a parent the operator has.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, NamedTuple

from opentelemetry import trace

if TYPE_CHECKING:
    from collections.abc import Generator

    from opentelemetry.trace import Span, SpanContext

# The keys a log line names the held Pipelex span under, in every sink that writes trace context: the
# OpenTelemetry attribute-namespace spelling, which the ``otlp`` sink needs as an attribute name anyway.
PIPELEX_TRACE_ID_KEY = "pipelex.trace_id"
PIPELEX_SPAN_ID_KEY = "pipelex.span_id"

# The Pipelex span active here; only ever a span naming a trace, since ``pipelex_span_active`` sets no other.
_ACTIVE_PIPELEX_SPAN: ContextVar[Span | None] = ContextVar("pipelex_active_span", default=None)


@contextmanager
def pipelex_span_active(*, span: Span | None, make_current: bool = False) -> Generator[None]:
    """Hold ``span`` as the Pipelex span active here while the block runs; no span, or one naming no trace, holds nothing.

    ``None`` is what the runtime holds with no tracer, in a dry run, or under a no-op tracer, the one
    ``OTEL_SDK_DISABLED`` hands out for one, which from ``opentelemetry-api`` 1.40 gives back the parent
    it was handed and before that an invalid span. A span naming no trace would hide the enclosing
    Pipelex span from every line of the block.

    OpenTelemetry's own context is left as it is unless ``make_current`` is true, which the runtime passes
    when the operator turned ``join_host_trace`` on: the span is then also OpenTelemetry's current span for
    the block, and the previous one comes back on the way out, however the block ends. Being made current
    never ends the span, records an exception on it or sets its status. The context is attached and
    detached in the same task, and a thread started inside the block by ``asyncio.to_thread`` copies it.
    """
    if span is None or not span.get_span_context().is_valid:
        yield
        return
    token = _ACTIVE_PIPELEX_SPAN.set(span)
    try:
        if make_current:
            with trace.use_span(span, end_on_exit=False, record_exception=False, set_status_on_exception=False):
                yield
        else:
            yield
    finally:
        _ACTIVE_PIPELEX_SPAN.reset(token)


class HostSpanToJoin(NamedTuple):
    """The current span a run joining the host's trace starts under, and whether it is a Pipelex span of this process."""

    span_context: SpanContext
    # True for a run started inside a running pipe whose span was made current: Pipelex's own streams receive that
    # span, so the run is a subtree of the enclosing run's trace rather than a new root in it.
    is_pipelex_span: bool


def host_span_to_join() -> HostSpanToJoin | None:
    """The current span a run joining the host's trace starts under, or ``None`` when no current span names a trace.

    Read once, at pipeline start, where the run's trace is decided; the job metadata carries the result from
    there, across a process boundary too. Inside a run whose spans are made current, the current span is the
    enclosing Pipelex span, the one held here, and the result says so.
    """
    current_span_context = trace.get_current_span().get_span_context()
    if not current_span_context.is_valid:
        return None
    pipelex_span_context = pipelex_span_context_for_logs()
    is_pipelex_span = (
        pipelex_span_context is not None
        and pipelex_span_context.trace_id == current_span_context.trace_id
        and pipelex_span_context.span_id == current_span_context.span_id
    )
    return HostSpanToJoin(span_context=current_span_context, is_pipelex_span=is_pipelex_span)


def current_span_context_for_logs() -> SpanContext | None:
    """OpenTelemetry's current span in the process, which a line's standard trace fields name, or ``None`` when it names no trace.

    The span is only read. A Pipelex span held here never stands in for it: inside a run with no current
    span of the host's, the standard fields are absent and the Pipelex span rides only under ``pipelex.*``.
    """
    current_span_context = trace.get_current_span().get_span_context()
    if current_span_context.is_valid:
        return current_span_context
    return None


def pipelex_span_context_for_logs() -> SpanContext | None:
    """The Pipelex span held here by ``pipelex_span_active``, the innermost one, or ``None`` outside any.

    OpenTelemetry's current span never stands in for it: outside a Pipelex span, a line carries no
    ``pipelex.*`` fields whatever the host's span is.
    """
    pipelex_span = _ACTIVE_PIPELEX_SPAN.get()
    if pipelex_span is None:
        return None
    return pipelex_span.get_span_context()


def pipelex_trace_fields_for_logs() -> dict[str, str]:
    """The ``pipelex.trace_id`` and ``pipelex.span_id`` of the Pipelex span held here, in lowercase hex at their full widths, or nothing.

    Written whenever a Pipelex span is held, even when it is also OpenTelemetry's current span, so a
    reader joining on these keys finds them on every line of a traced run whatever the process's setup.
    """
    span_context = pipelex_span_context_for_logs()
    if span_context is None:
        return {}
    return {
        PIPELEX_TRACE_ID_KEY: trace.format_trace_id(span_context.trace_id),
        PIPELEX_SPAN_ID_KEY: trace.format_span_id(span_context.span_id),
    }
