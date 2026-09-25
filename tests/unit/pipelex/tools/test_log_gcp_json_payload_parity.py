"""One field keeps one wire name whichever of the ``json`` and ``gcp`` sinks a process selects.

The ``gcp`` sink builds its own struct payload rather than rendering the ``json`` sink's line — the
client library carries the time and the severity out of band and wants a structure rather than
text — so the two spellings are two implementations of one contract, and nothing but a test holds them
together. Each case here renders the same record through both and compares, and each was a
disagreement before it was a test.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from google.cloud.logging_v2.handlers.transports.base import Transport
from typing_extensions import override

from pipelex.tools.log.gcp_log_sink import EXCEPTION_KEY, GcpLogHandler
from pipelex.tools.log.json_log_sink import JsonLogFormatter
from pipelex.tools.log.log_fields import attach_log_record_extra

PROJECT = "a-test-project"


class CapturingTransport(Transport):  # pyright: ignore[reportUntypedBaseClass]
    """The client library's transport contract, capturing the payload a comparison reads."""

    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    @override
    def send(  # kw-only: ignore — the sink calls the library's signature
        self,
        record: logging.LogRecord,
        message: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        self.payloads.append(message)

    @override
    def flush(self) -> None:
        return None

    @override
    def close(self) -> None:
        return None


class TestTheGcpAndJsonPayloadsAgree:
    @staticmethod
    def _both_payloads(record: logging.LogRecord) -> tuple[dict[str, Any], dict[str, Any]]:
        """The record as the ``json`` sink writes it and as the ``gcp`` sink hands it to the transport."""
        json_payload = json.loads(JsonLogFormatter().format(record))
        transport = CapturingTransport()
        GcpLogHandler(transport=transport, project=PROJECT).handle(record)
        (gcp_payload,) = transport.payloads
        return json_payload, gcp_payload

    @classmethod
    def _record(cls, *, fields: dict[str, Any] | None = None, exc_info: Any = None) -> logging.LogRecord:
        record = logging.LogRecord(name="my.module", level=logging.WARNING, pathname="", lineno=0, msg="hello", args=(), exc_info=exc_info)
        # Through the attach path the log call itself uses, so a name the record or the formatter
        # already owns is prefixed exactly once, where the sinks then see it.
        attach_log_record_extra(record=record, extra=fields or {})
        return record

    def test_a_field_named_like_a_key_only_the_json_sink_writes_is_prefixed_under_both(self) -> None:
        """``time`` and ``severity`` are not ``gcp`` payload keys, and a field named like one still keeps the ``json`` sink's wire name."""
        json_payload, gcp_payload = self._both_payloads(self._record(fields={"time": "mine", "severity": "mine"}))

        assert json_payload["field_time"] == "mine"
        assert json_payload["field_severity"] == "mine"
        assert gcp_payload["field_time"] == "mine"
        assert gcp_payload["field_severity"] == "mine"
        assert "time" not in gcp_payload
        assert "severity" not in gcp_payload

    def test_a_field_named_like_a_key_both_sinks_write_is_prefixed_under_both(self) -> None:
        json_payload, gcp_payload = self._both_payloads(self._record(fields={"message": "mine", "logger": "mine", "exception": "mine"}))

        for payload in (json_payload, gcp_payload):
            assert payload["message"] == "hello"
            assert payload["logger"] == "my.module"
            assert payload["field_message"] == "mine"
            assert payload["field_logger"] == "mine"
            assert payload["field_exception"] == "mine"

    def test_one_traceback_is_spelled_the_same_way_by_both_sinks(self) -> None:
        try:
            message = "kaput"
            raise ValueError(message)
        except ValueError:
            exc_info = sys.exc_info()
        json_payload, gcp_payload = self._both_payloads(self._record(exc_info=exc_info))

        assert "ValueError: kaput" in gcp_payload[EXCEPTION_KEY]
        assert gcp_payload[EXCEPTION_KEY] == json_payload[EXCEPTION_KEY]

    def test_an_exception_asked_for_outside_an_except_block_lands_under_both_sinks(self) -> None:
        """``logging.error(msg, exc_info=True)`` called with nothing in flight builds this triple, and a foreign library does it."""
        json_payload, gcp_payload = self._both_payloads(self._record(exc_info=(None, None, None)))

        assert gcp_payload[EXCEPTION_KEY] == json_payload[EXCEPTION_KEY]
