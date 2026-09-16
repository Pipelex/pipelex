"""The fields channel and the run-scoped log context.

A log call takes named ``fields`` and every record emitted inside ``with log.context(...)`` carries the
bound identifiers. Both ride the stdlib ``LogRecord`` as attributes, never spliced into the message,
so a structured sink renders them as fields while the console keeps its narrative line.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex import log
from pipelex.tools.log.log_context import LogContext, get_log_context
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, DATA_FIELD, STDLIB_LOG_RECORD_ATTRIBUTES
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

    def test_the_reserved_attribute_set_covers_what_the_stdlib_refuses(self) -> None:
        """Every attribute a fresh ``LogRecord`` carries, plus the two the formatter adds, is reserved."""
        probe = logging.LogRecord(name="probe", level=logging.INFO, pathname=__file__, lineno=1, msg="m", args=(), exc_info=None)
        assert set(vars(probe)) <= STDLIB_LOG_RECORD_ATTRIBUTES
        assert {"message", "asctime"} <= STDLIB_LOG_RECORD_ATTRIBUTES

    def test_a_field_overrides_the_context_for_that_record(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO), log.context(request_id="from-context"):
            log.info("about another request", fields={"request_id": "from-call-site"})
            log.info("about this request")

        override, plain = _own_records(caplog)
        assert _field(override, name="request_id") == "from-call-site"
        assert _field(plain, name="request_id") == "from-context"


class TestStructuredContent:
    def test_dict_content_is_carried_as_data_and_rendered_for_the_console(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info({"key": "value", "nested": {"flag": True}}, title="Config")

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == {"key": "value", "nested": {"flag": True}}
        rendered = record.getMessage()
        assert rendered.startswith("Config:")
        assert '"key": "value"' in rendered

    def test_list_content_is_carried_as_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info([1, "two", {"three": 3}])

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == [1, "two", {"three": 3}]

    def test_string_content_carries_no_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info("plain")

        (record,) = _own_records(caplog)
        assert not hasattr(record, DATA_FIELD)

    def test_structured_content_wins_over_a_data_field(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info({"from": "content"}, fields={DATA_FIELD: "from-field"})

        (record,) = _own_records(caplog)
        assert getattr(record, DATA_FIELD) == {"from": "content"}

    def test_none_content_is_rendered_as_the_word_none_without_data(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO):
            log.info(None, title="Empty")

        (record,) = _own_records(caplog)
        assert record.getMessage() == "Empty:\nNone"
        assert not hasattr(record, DATA_FIELD)


class TestLogContext:
    def test_context_yields_the_bound_context_and_restores_on_exit(self) -> None:
        assert get_log_context() is None
        with log.context(request_id="r1", pipeline_run_id="p1") as bound:
            assert bound == LogContext(request_id="r1", pipeline_run_id="p1")
            assert get_log_context() is bound
        assert get_log_context() is None

    def test_nested_contexts_merge_and_the_inner_overrides(self) -> None:
        with log.context(request_id="r1", pipeline_run_id="p1"):
            with log.context(pipeline_run_id="p2", pipe_run_id="pr1") as inner:
                assert inner == LogContext(request_id="r1", pipeline_run_id="p2", pipe_run_id="pr1")
            outer = get_log_context()
            assert outer == LogContext(request_id="r1", pipeline_run_id="p1")

    def test_a_none_identifier_inherits_rather_than_clears(self) -> None:
        with log.context(request_id="r1"), log.context(request_id=None, pipe_run_id="pr1") as inner:
            assert inner == LogContext(request_id="r1", pipe_run_id="pr1")

    def test_context_is_restored_when_the_block_raises(self) -> None:
        def explode() -> None:
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError), log.context(request_id="r1"):
            explode()
        assert get_log_context() is None

    def test_fields_of_a_context_omit_absent_identifiers(self) -> None:
        assert LogContext().fields == {}
        assert LogContext(pipeline_run_id="p1").fields == {"pipeline_run_id": "p1"}
        assert LogContext(request_id="r1", pipeline_run_id="p1", pipe_run_id="pr1").fields == {
            "request_id": "r1",
            "pipeline_run_id": "p1",
            "pipe_run_id": "pr1",
        }

    @pytest.mark.asyncio
    async def test_context_is_task_local(self, caplog: pytest.LogCaptureFixture) -> None:
        """Two concurrent tasks each see their own binding; neither leaks into the other or into the caller."""

        async def emit(request_id: str) -> None:
            with log.context(request_id=request_id):
                await asyncio.sleep(0)
                log.info("in task", fields={"tag": request_id})
                await asyncio.sleep(0)
                assert get_log_context() == LogContext(request_id=request_id)

        with caplog.at_level(logging.INFO):
            await asyncio.gather(emit("a"), emit("b"))

        assert get_log_context() is None
        records = _own_records(caplog)
        assert len(records) == 2
        for record in records:
            assert _field(record, name="request_id") == _field(record, name="tag")
