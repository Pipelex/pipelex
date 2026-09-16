"""The ``otlp`` sink: a record reaches an in-memory log exporter with the fields as attributes.

The sink is built on a synchronous processor so each record is exported before the assertion reads it;
production builds it on the batching processor and the OTLP HTTP exporter instead.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.semconv._incubating.attributes import code_attributes
from opentelemetry.semconv.attributes import exception_attributes

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.otlp_log_sink import OtlpLogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from opentelemetry.sdk._logs import LogData


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_logs(exporter: InMemoryLogExporter) -> list[LogData]:
    """The records this module emitted, whatever else the process logged meanwhile."""
    return [log_data for log_data in exporter.get_finished_logs() if log_data.instrumentation_scope.name == __name__]


def _attributes(log_data: LogData) -> dict[str, Any]:
    attributes = log_data.log_record.attributes
    assert attributes is not None
    return dict(attributes)


class TestOtlpLogSink:
    @pytest.fixture
    def otlp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, InMemoryLogExporter]]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        exporter = InMemoryLogExporter()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(OtlpLogSink(processor=SimpleLogRecordProcessor(exporter)))
        try:
            yield fresh, exporter
        finally:
            fresh.reset()

    def test_a_record_reaches_the_exporter_with_the_fields_and_the_context_as_attributes(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        with fresh.context(request_id="r1", pipe_run_id="pr1"):
            fresh.info("scanned", fields={"files": 7, "ratio": 0.5, "tags": ["a", "b"], "meta": {"k": "v"}})

        (log_data,) = _own_logs(exporter)
        record = log_data.log_record
        assert record.body == "scanned"
        assert record.severity_text == "INFO"
        assert record.severity_number is SeverityNumber.INFO
        attributes = _attributes(log_data)
        assert attributes["files"] == 7
        assert attributes["ratio"] == 0.5
        assert list(attributes["tags"]) == ["a", "b"]
        assert attributes["meta"] == '{"k": "v"}'
        assert attributes["request_id"] == "r1"
        assert attributes["pipe_run_id"] == "pr1"
        assert "pipeline_run_id" not in attributes
        assert attributes[code_attributes.CODE_FILE_PATH] == __file__
        assert attributes[code_attributes.CODE_FUNCTION_NAME] == "test_a_record_reaches_the_exporter_with_the_fields_and_the_context_as_attributes"
        assert attributes[code_attributes.CODE_LINE_NUMBER] > 0

    def test_structured_content_rides_as_json_text_in_the_data_attribute(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        fresh.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (log_data,) = _own_logs(exporter)
        assert _attributes(log_data)["data"] == '{"key": "value", "nested": {"flag": true}}'

    def test_the_exception_lands_under_the_semantic_convention_keys(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        fresh, exporter = otlp_log
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("failed", include_exception=True)

        (log_data,) = _own_logs(exporter)
        assert log_data.log_record.body == "failed"
        assert log_data.log_record.severity_number is SeverityNumber.ERROR
        attributes = _attributes(log_data)
        assert attributes[exception_attributes.EXCEPTION_TYPE] == "ValueError"
        assert attributes[exception_attributes.EXCEPTION_MESSAGE] == "boom"
        assert "Traceback (most recent call last)" in attributes[exception_attributes.EXCEPTION_STACKTRACE]

    @pytest.mark.parametrize(
        ("method_name", "severity_text", "severity_number"),
        [
            ("verbose", "VERBOSE", SeverityNumber.TRACE),
            ("debug", "DEBUG", SeverityNumber.DEBUG),
            ("dev", "DEV", SeverityNumber.DEBUG4),
            ("info", "INFO", SeverityNumber.INFO),
            ("warning", "WARN", SeverityNumber.WARN),
            ("error", "ERROR", SeverityNumber.ERROR),
            ("critical", "CRITICAL", SeverityNumber.FATAL),
        ],
    )
    def test_every_level_maps_onto_the_otel_severity_scale(
        self,
        otlp_log: tuple[Log, InMemoryLogExporter],
        caplog: pytest.LogCaptureFixture,
        method_name: str,
        severity_text: str,
        severity_number: SeverityNumber,
    ) -> None:
        fresh, exporter = otlp_log
        caplog.set_level(logging.NOTSET + 1, logger=__name__)
        getattr(fresh, method_name)("at every level")

        (log_data,) = _own_logs(exporter)
        assert log_data.log_record.severity_text == severity_text
        assert log_data.log_record.severity_number is severity_number

    def test_a_record_from_the_opentelemetry_sdk_itself_is_not_exported(self, otlp_log: tuple[Log, InMemoryLogExporter]) -> None:
        """An exporter's own failure line must not re-enter the pipeline that failed."""
        _, exporter = otlp_log
        logging.getLogger("opentelemetry.exporter.otlp").error("Failed to export logs batch")
        logging.getLogger("opentelemetry").warning("dropped")

        scopes = {log_data.instrumentation_scope.name for log_data in exporter.get_finished_logs()}
        assert not any(scope == "opentelemetry" or scope.startswith("opentelemetry.") for scope in scopes)
