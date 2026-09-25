"""The ``otlp`` sink files each record under the span current when it was logged.

The sink hands the current context to the SDK, which takes the record's trace id, span id and flags
from the span in it, so a collector files the record under that span; a record logged outside any
span carries none. A boot line held until the sink arrives keeps the span it was logged in. The sink
is built on a synchronous processor so each record is exported before the assertion reads it.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk._logs import LogRecord


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_records(exporter: InMemoryLogExporter) -> list[LogRecord]:
    """The records this module emitted, whatever else the process logged meanwhile."""
    return [log_data.log_record for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name == __name__]


class TestOtlpSinkTraceContext:
    @pytest.fixture
    def otlp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, InMemoryLogExporter]]:
        """A fresh ``Log`` with the otlp sink installed on an in-memory exporter, torn down so the root logger is left as found."""
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

        inside, outside = _own_records(exporter)
        assert inside.trace_id == span_context.trace_id
        assert inside.span_id == span_context.span_id
        assert inside.trace_flags == span_context.trace_flags
        assert outside.trace_id == 0
        assert outside.span_id == 0

    def test_a_boot_line_held_until_the_sink_arrives_keeps_the_span_it_was_logged_in(self, caplog: pytest.LogCaptureFixture) -> None:
        """The holding handler replays each record in the context it was emitted in, not in the one the install runs under."""
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        tracer = TracerProvider().get_tracer(__name__)
        try:
            with tracer.start_as_current_span("boot step") as boot_step:
                fresh.info("held inside a span")
            fresh.info("held outside any span")
            with tracer.start_as_current_span("install"):
                fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        finally:
            fresh.reset()

        inside, outside = _own_records(exporter)
        assert inside.span_id == boot_step.get_span_context().span_id
        assert outside.span_id == 0
