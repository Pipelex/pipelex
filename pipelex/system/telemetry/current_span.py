"""The two spans a log line names: OpenTelemetry's current span, and the Pipelex span active in this task.

A line's standard trace fields name OpenTelemetry's current span in the process, which Pipelex only
reads and never sets, so an operator's log backend files a line under the trace of the operator's own
spans. The Pipelex span rides beside them, under the ``pipelex.trace_id`` and ``pipelex.span_id`` keys,
so a line inside a run still names the pipe or the LLM call it was logged in. The two are read
independently: a line can carry both, either, or neither.

The runtime starts its spans with an explicit parent carried in the job metadata, because a run's trace
is derived from its business identifiers and has to survive a process boundary, where an in-process
context does not travel. A span started that way is current nowhere, and the runtime never makes it
OpenTelemetry's current span: Pipelex's tracer is its own and never the process's global one, so one of
its spans made current there would re-parent the host application's own instrumentation under a trace
only Pipelex's exporters receive, and have a sampler that follows its parent keep it. Instead, the
runtime holds the span in a context variable of its own while the work it measures runs, in this task
and in whatever copies the task's context, a thread started by ``asyncio.to_thread`` or a boot line the
holding handler replays, and restores the previous value on the way out. The log sinks read it to write
a line's ``pipelex.*`` fields, and nothing else does.

Holding a span never ends it, records an exception on it or sets its status, which stay with the code
that started it, and it never becomes the way a parent reaches a child: the job metadata still carries
that, so a child running in another process gets the same parent it always did.

An exception leaving a held span's block is marked with that span, the innermost one winning, and
:func:`raising_span_context` reads the mark back. A failure is reported after every span it crossed has
closed, the run's failure at the run's boundary for instance, so the error tracker names the span that
raised it from the mark rather than from the span held at the time of the report, which is none by then.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

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
def pipelex_span_active(*, span: Span | None) -> Generator[None]:
    """Hold ``span`` as the Pipelex span active here while the block runs; no span, or one naming no trace, holds nothing.

    ``None`` is what the runtime holds with no tracer, in a dry run, or under a no-op tracer, the one
    ``OTEL_SDK_DISABLED`` hands out for one, which from ``opentelemetry-api`` 1.40 gives back the parent
    it was handed and before that an invalid span. A span naming no trace would hide the enclosing
    Pipelex span from every line of the block. OpenTelemetry's own context is left as it is either way.
    """
    if span is None or not span.get_span_context().is_valid:
        yield
        return
    token = _ACTIVE_PIPELEX_SPAN.set(span)
    try:
        yield
    except BaseException as exc:
        # Observe-and-reraise: an exception leaving the block is marked with the span it was raised in, so whoever
        # reports it once every span has closed still names it. Marking never changes how the exception propagates.
        _stamp_raising_span(exception=exc, span_context=span.get_span_context())
        raise
    finally:
        _ACTIVE_PIPELEX_SPAN.reset(token)


# The attribute an exception carries the Pipelex span it was raised in under, set as it leaves that span.
_RAISING_SPAN_STAMP = "__pipelex_raising_span__"


def _stamp_raising_span(*, exception: BaseException, span_context: SpanContext) -> None:
    """Record on ``exception`` the Pipelex span it left, unless a span closer to where it was raised already did.

    The innermost span is the one the failing work ran in, so an existing stamp is never replaced. Stamping is
    best-effort and never raises: an exception whose class refuses the stamp to be read or written goes unstamped.
    """
    try:
        if hasattr(exception, _RAISING_SPAN_STAMP):
            return
        setattr(exception, _RAISING_SPAN_STAMP, span_context)
    except Exception:  # ruff: ignore[blind-except]
        # (2) reading and setting an attribute run the exception class's own `__getattribute__` and `__setattr__`, whose
        # exception surface cannot be enumerated (`__slots__` raise an AttributeError, a read-only class a TypeError, a
        # class of its own anything), and this runs while the exception propagates, so whatever they raise must never
        # replace it. Nothing is logged: the log sinks read this module, which therefore imports no logger.
        return


def _read_raising_span_stamp(*, exception: BaseException) -> object:
    """The raising-span stamp ``exception`` carries, or ``None`` when it carries none or refuses to be read; never raises."""
    try:
        return getattr(exception, _RAISING_SPAN_STAMP, None)
    except Exception:  # ruff: ignore[blind-except]
        # (2) reading an attribute runs the exception class's own `__getattribute__`, whose exception surface cannot be
        # enumerated; an exception that refuses to be read names no span.
        return None


def raising_span_context(*, exception: BaseException) -> SpanContext | None:
    """The Pipelex span ``exception`` was raised in, as it left that span's block, or ``None`` when it left none.

    Only ``exception`` itself is read; a reader walking a cause chain asks each of its errors in turn.
    """
    stamped = _read_raising_span_stamp(exception=exception)
    if isinstance(stamped, trace.SpanContext):
        return stamped
    return None


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
