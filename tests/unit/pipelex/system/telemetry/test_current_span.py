"""``pipelex_span_active`` holds a Pipelex span for a block, and the log readers read the two spans a line names.

A line's standard trace fields name OpenTelemetry's current span, which is only read, and its
``pipelex.*`` fields name the Pipelex span held in the task. The two are independent: a Pipelex span
held never hides the current span, and the current span never stands in for a Pipelex one.
OpenTelemetry's current context is never touched: inside the block the current span is whatever it was
outside, the host's or none. The span stays owned by the code that started it: the block never ends it,
never records an exception on it and never sets its status, even when an exception crosses the block
while the span is still recording, and the previous Pipelex span comes back on the way out, however the
block exits. A ``None`` span, which is what the runtime holds when it has no tracer, and a span naming
no trace, which is what a no-op tracer starts, hold nothing.
"""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, StatusCode, TraceFlags

from pipelex.system.telemetry.current_span import (
    PIPELEX_SPAN_ID_KEY,
    PIPELEX_TRACE_ID_KEY,
    current_span_context_for_logs,
    pipelex_span_active,
    pipelex_span_context_for_logs,
    pipelex_trace_fields_for_logs,
)

# A span whose ids are small enough that only a full-width, zero-padded spelling gets them right.
_SMALL_IDS_SPAN = NonRecordingSpan(SpanContext(trace_id=0xAB, span_id=0xCD, is_remote=False, trace_flags=TraceFlags(TraceFlags.SAMPLED)))


def _started_span(*, name: str) -> SdkSpan:
    span = TracerProvider().get_tracer(__name__).start_span(name)
    assert isinstance(span, SdkSpan)
    return span


def _fail_under(*, span: SdkSpan) -> None:
    with pipelex_span_active(span=span):
        msg = "boom"
        raise ValueError(msg)


class TestPipelexSpanActive:
    def test_the_innermost_pipelex_span_is_held_inside_the_block_and_the_previous_one_after(self) -> None:
        outer = _started_span(name="outer")
        inner = _started_span(name="inner")

        with pipelex_span_active(span=outer):
            with pipelex_span_active(span=inner):
                assert pipelex_span_context_for_logs() == inner.get_span_context()
            assert pipelex_span_context_for_logs() == outer.get_span_context()
        assert pipelex_span_context_for_logs() is None
        assert inner.is_recording()

    def test_opentelemetrys_current_span_is_never_touched(self) -> None:
        host = _started_span(name="host")
        pipelex_span = _started_span(name="pipe")

        with pipelex_span_active(span=pipelex_span):
            assert trace.get_current_span() is trace.INVALID_SPAN
        with trace.use_span(host), pipelex_span_active(span=pipelex_span):
            assert trace.get_current_span() is host

    def test_an_exception_crossing_the_block_leaves_the_span_as_it_was(self) -> None:
        span = _started_span(name="work")

        with pytest.raises(ValueError, match="boom"):
            _fail_under(span=span)

        assert pipelex_span_context_for_logs() is None
        assert span.is_recording()
        assert span.status.status_code is StatusCode.UNSET
        assert list(span.events) == []

    def test_a_none_span_holds_nothing(self) -> None:
        enclosing = _started_span(name="enclosing")

        with pipelex_span_active(span=None):
            assert pipelex_span_context_for_logs() is None
        with pipelex_span_active(span=enclosing), pipelex_span_active(span=None):
            assert pipelex_span_context_for_logs() == enclosing.get_span_context()

    def test_a_span_naming_no_trace_does_not_hide_the_enclosing_pipelex_span(self) -> None:
        """What a no-op tracer starts, under ``OTEL_SDK_DISABLED`` for one, must not hide a valid span."""
        enclosing = _started_span(name="enclosing")

        with pipelex_span_active(span=trace.INVALID_SPAN):
            assert pipelex_span_context_for_logs() is None
        with pipelex_span_active(span=enclosing), pipelex_span_active(span=trace.INVALID_SPAN):
            assert pipelex_span_context_for_logs() == enclosing.get_span_context()


class TestCurrentSpanForLogs:
    def test_the_hosts_current_span_is_read_inside_and_outside_a_pipelex_span(self) -> None:
        host = _started_span(name="host")
        pipelex_span = _started_span(name="pipe")

        with trace.use_span(host):
            assert current_span_context_for_logs() == host.get_span_context()
            with pipelex_span_active(span=pipelex_span):
                assert current_span_context_for_logs() == host.get_span_context()

    def test_a_pipelex_span_never_stands_in_for_a_missing_current_span(self) -> None:
        with pipelex_span_active(span=_started_span(name="pipe")):
            assert current_span_context_for_logs() is None

    def test_a_current_span_naming_no_trace_reads_as_none(self) -> None:
        assert current_span_context_for_logs() is None
        with trace.use_span(trace.INVALID_SPAN):
            assert current_span_context_for_logs() is None


class TestPipelexSpanForLogs:
    def test_the_hosts_current_span_never_stands_in_for_a_missing_pipelex_span(self) -> None:
        with trace.use_span(_started_span(name="host")):
            assert pipelex_span_context_for_logs() is None

    def test_the_held_pipelex_span_is_read_under_the_hosts_current_span(self) -> None:
        pipelex_span = _started_span(name="pipe")

        with trace.use_span(_started_span(name="host")), pipelex_span_active(span=pipelex_span):
            assert pipelex_span_context_for_logs() == pipelex_span.get_span_context()


class TestPipelexTraceFieldsForLogs:
    def test_the_held_span_is_written_as_both_ids_in_lowercase_hex(self) -> None:
        pipelex_span = _started_span(name="pipe")
        span_context = pipelex_span.get_span_context()
        assert span_context is not None

        with pipelex_span_active(span=pipelex_span):
            fields = pipelex_trace_fields_for_logs()

        assert fields == {
            PIPELEX_TRACE_ID_KEY: f"{span_context.trace_id:032x}",
            PIPELEX_SPAN_ID_KEY: f"{span_context.span_id:016x}",
        }

    def test_the_ids_are_zero_padded_to_their_full_widths(self) -> None:
        with pipelex_span_active(span=_SMALL_IDS_SPAN):
            fields = pipelex_trace_fields_for_logs()

        assert fields == {PIPELEX_TRACE_ID_KEY: "000000000000000000000000000000ab", PIPELEX_SPAN_ID_KEY: "00000000000000cd"}

    def test_no_held_span_writes_nothing_even_under_the_hosts_current_span(self) -> None:
        assert pipelex_trace_fields_for_logs() == {}
        with trace.use_span(_started_span(name="host")):
            assert pipelex_trace_fields_for_logs() == {}

    def test_the_keys_are_namespaced_under_pipelex(self) -> None:
        assert PIPELEX_TRACE_ID_KEY == "pipelex.trace_id"
        assert PIPELEX_SPAN_ID_KEY == "pipelex.span_id"
