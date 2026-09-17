"""What the ``gcp`` sink assumes of ``google-cloud-logging``, asserted against the installed library.

The sink declares the transport's shape rather than importing it, it computes the severity itself
rather than letting the library derive one from the level, because the library's own normalization has
no spelling for our ``VERBOSE`` and ``DEV``, and it rejects the library's own export path by the logger
names and the thread name the library chooses. Every one of those is an assumption about a third party
whose change would break a production sink silently and no other test would see: a renamed worker
thread or a renamed transport logger would let a refused batch be reported through the pipeline that
refused it, which is a spin that never ends and a deadlock at exit.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from google.cloud.logging_v2.entries import StructEntry
from google.cloud.logging_v2.handlers.transports.background_thread import (
    _WORKER_THREAD_NAME,  # pyright: ignore[reportPrivateUsage]
    _Worker,  # pyright: ignore[reportPrivateUsage]
)
from google.cloud.logging_v2.handlers.transports.base import Transport

from pipelex.tools.log.gcp_log_sink import (
    GCP_LOGGING_LOGGER_PREFIXES,
    GCP_WORKER_THREAD_NAME,
    MESSAGE_KEY,
    GcpLogSeverity,
    trace_name_for_run,
)


class TestTheClientLibraryContract:
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

    def test_the_export_thread_still_carries_the_name_the_sinks_guard_rejects(self) -> None:
        assert GCP_WORKER_THREAD_NAME == _WORKER_THREAD_NAME

    def test_the_transport_reports_a_refused_batch_under_a_logger_the_guard_rejects(self) -> None:
        """The report the loop is made of: an ``ERROR`` on the library's own logger, propagating to the root."""
        transport_logger = logging.getLogger("google.cloud.logging_v2.handlers.transports.background_thread")
        assert any(transport_logger.name == prefix or transport_logger.name.startswith(f"{prefix}.") for prefix in GCP_LOGGING_LOGGER_PREFIXES)
        assert transport_logger.propagate
        assert transport_logger.isEnabledFor(logging.ERROR)
