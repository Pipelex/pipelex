"""``pipelex_span_active`` holds a Pipelex span for a block, where the ``pipelex.*`` log fields read it.

OpenTelemetry's current context is never touched: inside the block the current span is whatever it was
outside, the host's or none. The span stays owned by the code that started it: the block never ends it,
never records an exception on it and never sets its status, even when an exception crosses the block
while the span is still recording, and the previous Pipelex span comes back on the way out, however the
block exits. A ``None`` span, which is what the runtime holds when it has no tracer, and a span naming
no trace, which is what a no-op tracer starts, hold nothing.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SdkSpan
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import StatusCode
from typing_extensions import override

from pipelex.system.telemetry.current_span import pipelex_span_active, pipelex_span_context_for_logs, raising_span_context

# The prefix of the attributes the runtime marks an exception with, the Pipelex span it left among them.
_PIPELEX_MARK_PREFIX = "__pipelex_"


class _UnreadableStampError(Exception):
    """An exception whose class's ``__getattribute__`` raises when the runtime's marks are read."""

    @override
    def __getattribute__(self, name: str) -> Any:
        if name.startswith(_PIPELEX_MARK_PREFIX):
            msg = "this error's attributes cannot be read"
            raise RuntimeError(msg)
        return super().__getattribute__(name)


class _UnstampableError(Exception):
    """An exception whose class's ``__setattr__`` raises, other than an AttributeError or a TypeError, when the runtime marks it."""

    @override
    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith(_PIPELEX_MARK_PREFIX):
            msg = "this error's attributes cannot be set"
            raise RuntimeError(msg)
        super().__setattr__(name, value)


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

    def test_an_exception_leaving_the_block_is_marked_with_the_span_it_was_raised_in(self) -> None:
        span = _started_span(name="work")

        with pytest.raises(ValueError, match="boom") as exc_info:
            _fail_under(span=span)

        assert raising_span_context(exception=exc_info.value) == span.get_span_context()

    def test_the_innermost_span_wins_over_the_ones_the_exception_crosses_on_its_way_out(self) -> None:
        outer = _started_span(name="outer")
        inner = _started_span(name="inner")

        with pytest.raises(ValueError, match="boom") as exc_info, pipelex_span_active(span=outer):
            _fail_under(span=inner)

        assert raising_span_context(exception=exc_info.value) == inner.get_span_context()

    def test_an_exception_raised_outside_every_span_carries_no_mark(self) -> None:
        assert raising_span_context(exception=ValueError("boom")) is None

    @pytest.mark.parametrize("error_class", [_UnreadableStampError, _UnstampableError])
    def test_an_exception_whose_class_refuses_the_stamp_leaves_the_block_as_itself(self, error_class: type[Exception]) -> None:
        """Stamping runs the exception class's own code; whatever it raises, the exception that left the block is the one raised."""
        span = _started_span(name="work")

        msg = "boom"
        with pytest.raises(error_class, match=msg) as exc_info, pipelex_span_active(span=span):
            raise error_class(msg)

        assert raising_span_context(exception=exc_info.value) is None
