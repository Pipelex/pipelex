"""The fields channel of a log call.

A log call takes named ``fields``, and every record emitted inside ``with log.context(...)`` carries the
bound identifiers beside them. Both ride the stdlib ``LogRecord`` as attributes, never spliced into the
message, so a structured sink renders them as fields while the console keeps its narrative line. A name
the record already owns is carried under a prefix rather than raising.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex import log
from pipelex.tools.log.log_context import get_log_context
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, DATA_FIELD
from pipelex.tools.log.log_levels import LOGGING_LEVEL_VERBOSE

if TYPE_CHECKING:
    from collections.abc import Callable


def _own_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    """The records this test module emitted, whatever else the session's handlers saw."""
    return [record for record in caplog.records if record.name == __name__]


def _field(record: logging.LogRecord, *, name: str) -> Any:
    """A field carried on the record: an attribute the stdlib does not declare, read the way a sink reads it."""
    return getattr(record, name)


class TestLogFields:
    def test_fields_and_context_ride_the_record_as_attributes(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO), log.context(request_id="r1", pipeline_run_id="p1"):
            log.info("scanned the inputs", fields={"files": 7})

        (record,) = _own_records(caplog)
        assert _field(record, name="files") == 7
        assert _field(record, name="request_id") == "r1"
        assert _field(record, name="pipeline_run_id") == "p1"
        assert not hasattr(record, "pipe_run_id")
        message = record.getMessage()
        assert message == "scanned the inputs"
        assert "r1" not in message
        assert "p1" not in message
        assert "7" not in message

    def test_a_record_outside_any_context_carries_no_identifier(self, caplog: pytest.LogCaptureFixture) -> None:
        assert get_log_context() is None
        with caplog.at_level(logging.INFO):
            log.info("outside", fields={"files": 7})

        (record,) = _own_records(caplog)
        assert _field(record, name="files") == 7
        assert not hasattr(record, "request_id")
        assert not hasattr(record, "pipeline_run_id")
        assert not hasattr(record, "pipe_run_id")
        assert "None" not in record.getMessage()

    @pytest.mark.parametrize(
        ("level", "method_name"),
        [
            (LOGGING_LEVEL_VERBOSE, "verbose"),
            (logging.DEBUG, "debug"),
            (15, "dev"),
            (logging.INFO, "info"),
            (logging.WARNING, "warning"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "critical"),
        ],
    )
    def test_every_level_takes_fields(self, caplog: pytest.LogCaptureFixture, level: int, method_name: str) -> None:
        method: Callable[..., None] = getattr(log, method_name)
        with caplog.at_level(LOGGING_LEVEL_VERBOSE), log.context(pipe_run_id="pr1"):
            method("at every level", fields={"attempt": 2})

        (record,) = _own_records(caplog)
        assert record.levelno == level
        assert _field(record, name="attempt") == 2
        assert _field(record, name="pipe_run_id") == "pr1"
        assert record.getMessage() == "at every level"

    def test_title_and_inline_keep_their_meaning_beside_fields(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info("body", title="Heading", fields={"k": "v"})
            log.info("body", inline="Tag", fields={"k": "v"})

        titled, inlined = _own_records(caplog)
        assert titled.getMessage() == "Heading:\nbody"
        assert inlined.getMessage() == "Tag: body"
        assert _field(titled, name="k") == "v"
        assert _field(inlined, name="k") == "v"

    def test_a_field_named_like_a_stdlib_record_attribute_is_prefixed_not_raised(self, caplog: pytest.LogCaptureFixture) -> None:
        """The stdlib raises ``KeyError`` when ``extra`` overwrites a record attribute; a log call never raises."""
        with caplog.at_level(logging.INFO):
            log.info("collision", fields={"name": "not-the-logger", "message": "not-the-message", "lineno": -1, "safe": 1})

        (record,) = _own_records(caplog)
        assert record.name == __name__
        assert record.getMessage() == "collision"
        assert record.lineno > 0
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}name") == "not-the-logger"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}message") == "not-the-message"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}lineno") == -1
        assert _field(record, name="safe") == 1

    def test_an_attribute_a_record_factory_added_is_a_collision_too(self, caplog: pytest.LogCaptureFixture) -> None:
        """A record factory (an OpenTelemetry or tracing instrumentation) stamps attributes the stdlib never declared.

        The collision is read off the record actually built, so a field, a context identifier or the
        ``data`` attribute named like one is prefixed rather than raising ``KeyError`` out of the log call.
        """
        previous_factory = logging.getLogRecordFactory()

        def stamping_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous_factory(*args, **kwargs)
            record.otelTraceID = "trace-from-factory"
            record.request_id = "request-from-factory"
            record.data = "data-from-factory"
            return record

        logging.setLogRecordFactory(stamping_factory)
        try:
            with caplog.at_level(logging.INFO), log.context(request_id="r1"):
                log.info({"key": "value"}, fields={"otelTraceID": "trace-from-call"})
        finally:
            logging.setLogRecordFactory(previous_factory)

        (record,) = _own_records(caplog)
        assert _field(record, name="otelTraceID") == "trace-from-factory"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}otelTraceID") == "trace-from-call"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}request_id") == "r1"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}{DATA_FIELD}") == {"key": "value"}

    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            pytest.param(
                {"name": "alpha", "field_name": "beta"},
                {f"{COLLIDING_FIELD_PREFIX}name": "alpha", f"{COLLIDING_FIELD_PREFIX}{COLLIDING_FIELD_PREFIX}name": "beta"},
                id="colliding-name-first",
            ),
            pytest.param(
                {"field_name": "beta", "name": "alpha"},
                {f"{COLLIDING_FIELD_PREFIX}name": "beta", f"{COLLIDING_FIELD_PREFIX}{COLLIDING_FIELD_PREFIX}name": "alpha"},
                id="prefixed-name-first",
            ),
            pytest.param(
                {"field_message": "given", "message": "colliding"},
                {f"{COLLIDING_FIELD_PREFIX}message": "given", f"{COLLIDING_FIELD_PREFIX}{COLLIDING_FIELD_PREFIX}message": "colliding"},
                id="formatter-owned-prefixed-first",
            ),
        ],
    )
    def test_a_prefixed_name_that_is_itself_given_loses_no_value(
        self, caplog: pytest.LogCaptureFixture, fields: dict[str, str], expected: dict[str, str]
    ) -> None:
        """Whichever of ``name`` and ``field_name`` arrives first keeps ``field_name``; the other lands on ``field_field_name``."""
        with caplog.at_level(logging.INFO):
            log.info("both given", fields=fields)

        (record,) = _own_records(caplog)
        assert record.name == __name__
        assert record.getMessage() == "both given"
        for attribute, value in expected.items():
            assert getattr(record, attribute) == value

    def test_a_factory_owning_the_prefixed_name_too_loses_neither_value(self, caplog: pytest.LogCaptureFixture) -> None:
        """A factory that stamps both ``request_id`` and ``field_request_id`` keeps both; the bound identifier lands one prefix further."""
        previous_factory = logging.getLogRecordFactory()

        def stamping_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous_factory(*args, **kwargs)
            record.request_id = "request-from-factory"
            record.field_request_id = "prefixed-from-factory"
            return record

        logging.setLogRecordFactory(stamping_factory)
        try:
            with caplog.at_level(logging.INFO), log.context(request_id="r1"):
                log.info("bound under a factory")
        finally:
            logging.setLogRecordFactory(previous_factory)

        (record,) = _own_records(caplog)
        assert _field(record, name="request_id") == "request-from-factory"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}request_id") == "prefixed-from-factory"
        assert getattr(record, f"{COLLIDING_FIELD_PREFIX}{COLLIDING_FIELD_PREFIX}request_id") == "r1"

    def test_a_field_overrides_the_context_for_that_record(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO), log.context(request_id="from-context"):
            log.info("about another request", fields={"request_id": "from-call-site"})
            log.info("about this request")

        override, plain = _own_records(caplog)
        assert _field(override, name="request_id") == "from-call-site"
        assert _field(plain, name="request_id") == "from-context"
