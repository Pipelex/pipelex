"""The ``gcp`` sink: a record reaches the Cloud Logging transport as one struct entry.

The sink is built around a fake transport, a subclass of the client library's own ``Transport``, so
each entry is captured where the library would have batched it; production builds it on the
``BackgroundThreadTransport`` around a real client instead. A second class pins what the sink assumes
of the library itself: the transport methods it calls, and that the severity it computes is the one
that lands on the entry rather than the one the library derives from the level.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import pytest
from google.cloud.logging_v2.entries import StructEntry
from google.cloud.logging_v2.handlers.transports.background_thread import _Worker  # pyright: ignore[reportPrivateUsage]
from google.cloud.logging_v2.handlers.transports.base import Transport
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.gcp_log_sink import (
    EXCEPTION_KEY,
    LOGGER_KEY,
    MESSAGE_KEY,
    GcpLogSeverity,
    GcpLogSink,
    severity_for_level,
    trace_name_for_run,
)
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.misc.hash_utils import hash_md5_to_int
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

PROJECT = "a-test-project"


class CapturedEntry:
    """One entry the sink handed the transport, as the transport received it."""

    def __init__(self, *, record: logging.LogRecord, payload: dict[str, Any], kwargs: dict[str, Any]) -> None:
        self.record = record
        self.payload = payload
        self.severity: Any = kwargs.get("severity")
        self.labels: dict[str, str] = kwargs.get("labels") or {}
        self.trace: str | None = kwargs.get("trace")


class FakeTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """The client library's transport contract, capturing instead of batching to the API."""

    def __init__(self) -> None:
        self.entries: list[CapturedEntry] = []
        self.flush_count = 0
        self.close_count = 0

    @override
    def send(self, record: logging.LogRecord, message: dict[str, Any], **kwargs: Any) -> None:  # kw-only: ignore — the library's own signature
        self.entries.append(CapturedEntry(record=record, payload=message, kwargs=kwargs))

    @override
    def flush(self) -> None:
        self.flush_count += 1

    @override
    def close(self) -> None:
        self.close_count += 1


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_entries(transport: FakeTransport) -> list[CapturedEntry]:
    """The entries this module's own records produced, whatever else the process logged meanwhile."""
    return [entry for entry in transport.entries if entry.record.name == __name__]


class TestGcpLogSink:
    @pytest.fixture
    def gcp_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, FakeTransport]]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        transport = FakeTransport()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(GcpLogSink(transport=transport, project=PROJECT))
        try:
            yield fresh, transport
        finally:
            fresh.reset()

    def test_the_message_and_the_fields_land_in_the_struct_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("scanned", fields={"files": 7, "ratio": 0.5, "tags": ["a", "b"], "meta": {"k": "v"}})

        (entry,) = _own_entries(transport)
        assert entry.payload[MESSAGE_KEY] == "scanned"
        assert entry.payload[LOGGER_KEY] == __name__
        assert entry.payload["files"] == 7
        assert entry.payload["ratio"] == 0.5
        assert entry.payload["tags"] == ["a", "b"]
        assert entry.payload["meta"] == {"k": "v"}
        assert entry.severity == GcpLogSeverity.INFO.value

    def test_the_run_scoped_identifiers_become_labels_and_stay_out_of_the_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        with fresh.context(request_id="r1", pipe_run_id="pr1"):
            fresh.info("bound")

        (entry,) = _own_entries(transport)
        assert entry.labels == {"request_id": "r1", "pipe_run_id": "pr1"}
        assert "request_id" not in entry.payload
        assert "pipe_run_id" not in entry.payload

    def test_the_trace_field_carries_the_runs_own_trace_id_project_qualified(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        with fresh.context(pipeline_run_id="plr-01"):
            fresh.info("running")

        (entry,) = _own_entries(transport)
        assert entry.trace == f"projects/{PROJECT}/traces/{hash_md5_to_int('plr-01'):032x}"
        assert entry.labels == {"pipeline_run_id": "plr-01"}

    def test_a_record_outside_any_run_carries_no_trace_and_no_labels(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("unbound")

        (entry,) = _own_entries(transport)
        assert entry.trace is None
        assert entry.labels == {}

    def test_structured_content_rides_in_the_data_key_of_the_payload(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (entry,) = _own_entries(transport)
        assert entry.payload["data"] == {"key": "value", "nested": {"flag": True}}

    def test_a_value_json_cannot_carry_is_written_as_text_rather_than_costing_the_line(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        circular: dict[str, Any] = {}
        circular["self"] = circular
        fresh.info("odd values", fields={"nan": float("nan"), "inf": float("inf"), "circular": circular})

        (entry,) = _own_entries(transport)
        assert entry.payload[MESSAGE_KEY] == "odd values"
        assert entry.payload["nan"] == "NaN"
        assert entry.payload["inf"] == "Infinity"
        assert isinstance(entry.payload["circular"], str)

    def test_a_field_named_like_a_fixed_key_keeps_its_value_under_the_prefix(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        fresh.info("the message", fields={"logger": "mine"})

        (entry,) = _own_entries(transport)
        assert entry.payload[LOGGER_KEY] == __name__
        assert entry.payload["field_logger"] == "mine"

    def test_the_exception_lands_under_the_exception_key(self, gcp_log: tuple[Log, FakeTransport]) -> None:
        fresh, transport = gcp_log
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("failed", include_exception=True)

        (entry,) = _own_entries(transport)
        assert entry.severity == GcpLogSeverity.ERROR.value
        assert "Traceback (most recent call last)" in entry.payload[EXCEPTION_KEY]
        assert "ValueError: boom" in entry.payload[EXCEPTION_KEY]

    @pytest.mark.parametrize(
        ("method_name", "severity"),
        [
            ("verbose", GcpLogSeverity.DEBUG),
            ("debug", GcpLogSeverity.DEBUG),
            ("dev", GcpLogSeverity.DEBUG),
            ("info", GcpLogSeverity.INFO),
            ("warning", GcpLogSeverity.WARNING),
            ("error", GcpLogSeverity.ERROR),
            ("critical", GcpLogSeverity.CRITICAL),
        ],
    )
    def test_every_level_maps_onto_the_cloud_logging_severity_scale(
        self,
        gcp_log: tuple[Log, FakeTransport],
        caplog: pytest.LogCaptureFixture,
        method_name: str,
        severity: GcpLogSeverity,
    ) -> None:
        fresh, transport = gcp_log
        caplog.set_level(logging.NOTSET + 1, logger=__name__)
        getattr(fresh, method_name)("at every level")

        (entry,) = _own_entries(transport)
        assert entry.severity == severity.value

    def test_the_teardown_flushes_and_closes_the_transport(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=__name__)
        transport = FakeTransport()
        fresh = Log()
        fresh.configure(log_config=_package_log_config())
        fresh.install_sink(GcpLogSink(transport=transport, project=PROJECT))
        fresh.reset()

        assert transport.flush_count > 0
        assert transport.close_count == 1


class TestGcpLogSinkMapping:
    """The two mappings the sink owns, read without a handler in the way."""

    def test_the_two_custom_levels_land_on_debug(self) -> None:
        assert severity_for_level(levelno=5) is GcpLogSeverity.DEBUG
        assert severity_for_level(levelno=15) is GcpLogSeverity.DEBUG

    def test_a_level_above_critical_still_maps_to_critical(self) -> None:
        assert severity_for_level(levelno=logging.CRITICAL + 10) is GcpLogSeverity.CRITICAL

    def test_the_trace_name_is_the_tracers_own_id_in_32_hex_digits(self) -> None:
        trace_name = trace_name_for_run(project="p", pipeline_run_id="plr-42")
        prefix, _, trace_id = trace_name.rpartition("/")
        assert prefix == "projects/p/traces"
        assert len(trace_id) == 32
        assert int(trace_id, 16) == hash_md5_to_int("plr-42")


class TestTheClientLibraryContract:
    """What the sink assumes of ``google-cloud-logging``, asserted against the installed library.

    The sink declares the transport's shape rather than importing it, and it computes the severity
    itself rather than letting the library derive one from the level, because the library's own
    normalization has no spelling for our ``VERBOSE`` and ``DEV``. Both are assumptions about a third
    party whose change would break a production sink silently and no other test would see.
    """

    def test_the_transport_still_carries_the_three_methods_the_sink_calls(self) -> None:
        for method_name in ("send", "flush", "close"):
            assert callable(getattr(Transport, method_name))

    def test_the_severity_the_sink_passes_overrides_the_one_the_library_derives_from_the_level(self) -> None:
        # The worker only holds the logger for its own thread, which is never started here, so the
        # queued entry can be read without a client.
        worker: Any = _Worker(object())
        record = logging.LogRecord(name="pipelex", level=5, pathname="", lineno=0, msg="verbose line", args=(), exc_info=None)
        worker.enqueue(record, {MESSAGE_KEY: "verbose line"}, severity=GcpLogSeverity.DEBUG.value, labels={}, trace=None)

        queued = cast("dict[str, Any]", worker._queue.get_nowait())  # ruff: ignore[private-member-access]
        assert queued["severity"] == GcpLogSeverity.DEBUG.value
        assert queued["message"] == {MESSAGE_KEY: "verbose line"}
        assert queued["labels"]["python_logger"] == "pipelex"

    def test_a_struct_entry_renders_the_severity_name_and_the_trace_the_sink_passes(self) -> None:
        trace_name = trace_name_for_run(project="p", pipeline_run_id="plr-1")
        # The library builds its entries from a namedtuple whose fields mypy does not see.
        entry: Any = StructEntry(payload={MESSAGE_KEY: "m"}, severity=GcpLogSeverity.WARNING.value, trace=trace_name)  # type: ignore[call-arg]

        api_repr = cast("dict[str, Any]", entry.to_api_repr())
        assert api_repr["severity"] == GcpLogSeverity.WARNING.value
        assert api_repr["trace"] == trace_name
