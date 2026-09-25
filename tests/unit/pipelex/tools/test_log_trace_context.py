"""Both wire sinks carry the trace context of the span current when a record is logged.

The ``json`` sink writes it under the keys OpenTelemetry specifies for trace context in a JSON log that
is not OTLP, ``trace_id``, ``span_id`` and ``trace_flags``, lowercase hex at their full widths; the
``otlp`` sink hands the current context to the SDK, which files the record under the span. A record
logged outside any valid span carries none of it. The records go the whole way, from the facade
through the module-named logger to the sink's handler, on a fresh ``Log`` so the installed sink is the
one under test and the teardown leaves the root logger as it found it.
"""

from __future__ import annotations

import io
import json
import logging
import re
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry import trace
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.json_log_sink import (
    LOGGER_KEY,
    MESSAGE_KEY,
    SEVERITY_KEY,
    SPAN_ID_KEY,
    TIME_KEY,
    TRACE_FLAGS_KEY,
    TRACE_ID_KEY,
    JsonLogSink,
)
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk._logs import LogData

TRACE_KEYS: tuple[str, ...] = (TRACE_ID_KEY, SPAN_ID_KEY, TRACE_FLAGS_KEY)

# A span context whose ids are small enough that only a full-width, zero-padded spelling gets them right,
# and which is not sampled, so its flags are written as they are rather than as the sampled default.
_UNSAMPLED_SPAN_CONTEXT = SpanContext(trace_id=0xAB, span_id=0xCD, is_remote=False, trace_flags=TraceFlags(TraceFlags.DEFAULT))


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    """Every line this module emitted, each parsed as one JSON object, whatever else the process logged meanwhile."""
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return [line for line in lines if line[LOGGER_KEY] == __name__]


def _own_logs(exporter: InMemoryLogExporter) -> list[LogData]:
    """The records this module emitted, whatever else the process logged meanwhile."""
    return [log_data for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name == __name__]


class TestJsonSinkTraceContext:
    @pytest.fixture
    def json_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, io.StringIO]]:
        """A fresh ``Log`` with the json sink installed on a buffer, torn down so the root logger is left as found."""
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(JsonLogSink(stream=buffer))
        try:
            yield fresh, buffer
        finally:
            fresh.reset()

    def test_a_line_logged_inside_a_span_carries_its_trace_context_in_hex(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("work") as span:
            fresh.info("inside")
        span_context = span.get_span_context()

        (line,) = _own_lines(buffer)
        assert line[TRACE_ID_KEY] == f"{span_context.trace_id:032x}"
        assert line[SPAN_ID_KEY] == f"{span_context.span_id:016x}"
        assert line[TRACE_FLAGS_KEY] == "01"
        assert re.fullmatch(r"[0-9a-f]{32}", line[TRACE_ID_KEY])
        assert re.fullmatch(r"[0-9a-f]{16}", line[SPAN_ID_KEY])

    def test_a_line_logged_outside_any_span_carries_none_of_the_keys(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        fresh.info("outside")

        (line,) = _own_lines(buffer)
        assert not set(TRACE_KEYS) & set(line)

    def test_an_invalid_current_span_writes_nothing(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A context can hold a span that names no trace; a line under it is a line outside any span."""
        fresh, buffer = json_log
        with trace.use_span(trace.INVALID_SPAN):
            fresh.info("under the invalid span")

        (line,) = _own_lines(buffer)
        assert not set(TRACE_KEYS) & set(line)

    def test_the_ids_are_zero_padded_and_the_flags_written_as_they_are(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("unsampled")

        (line,) = _own_lines(buffer)
        assert line[TRACE_ID_KEY] == "000000000000000000000000000000ab"
        assert line[SPAN_ID_KEY] == "00000000000000cd"
        assert line[TRACE_FLAGS_KEY] == "00"

    def test_the_line_leaving_the_span_no_longer_carries_it(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("outer") as outer:
            with tracer.start_as_current_span("inner") as inner:
                fresh.info("in the inner span")
            fresh.info("back in the outer span")
        fresh.info("after both")

        in_inner, in_outer, after = _own_lines(buffer)
        assert in_inner[SPAN_ID_KEY] == f"{inner.get_span_context().span_id:016x}"
        assert in_outer[SPAN_ID_KEY] == f"{outer.get_span_context().span_id:016x}"
        assert in_inner[TRACE_ID_KEY] == in_outer[TRACE_ID_KEY]
        assert not set(TRACE_KEYS) & set(after)

    def test_the_trace_keys_follow_the_fixed_keys_and_precede_the_fields(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("ordered", fields={"files": 7})

        (line,) = _own_lines(buffer)
        assert list(line) == [TIME_KEY, SEVERITY_KEY, LOGGER_KEY, MESSAGE_KEY, TRACE_ID_KEY, SPAN_ID_KEY, TRACE_FLAGS_KEY, "files"]

    def test_the_trace_keys_are_reserved_with_or_without_a_span(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A field named like a trace key is prefixed on every line, so its wire name never depends on a span being current."""
        fresh, buffer = json_log
        supplied = dict.fromkeys(TRACE_KEYS, "supplied")
        fresh.info("no span", fields=supplied)
        with trace.use_span(NonRecordingSpan(_UNSAMPLED_SPAN_CONTEXT)):
            fresh.info("in a span", fields=supplied)

        without_span, with_span = _own_lines(buffer)
        for key in TRACE_KEYS:
            assert key not in without_span
            assert without_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
            assert with_span[f"{COLLIDING_FIELD_PREFIX}{key}"] == "supplied"
        assert with_span[TRACE_ID_KEY] == "000000000000000000000000000000ab"


class TestOtlpSinkTraceContext:
    @pytest.fixture
    def otlp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, InMemoryLogExporter]]:
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        try:
            yield fresh, exporter
        finally:
            fresh.reset()

    def test_a_record_logged_inside_a_span_is_filed_under_it(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        tracer = TracerProvider().get_tracer(__name__)
        with tracer.start_as_current_span("work") as span:
            fresh.info("inside")
        fresh.info("outside")
        span_context = span.get_span_context()

        inside, outside = (log_data.log_record for log_data in _own_logs(exporter))
        assert inside.trace_id == span_context.trace_id
        assert inside.span_id == span_context.span_id
        assert inside.trace_flags == span_context.trace_flags
        assert outside.trace_id == 0
        assert outside.span_id == 0
