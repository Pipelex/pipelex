"""The ``json`` sink: one JSON object per line, parsed back, with the fields, the context and the exception.

The records go the whole way, from the facade through the module-named logger to the sink's handler,
on a fresh ``Log`` so the installed sink is the one under test and the teardown leaves the root logger
as it found it.
"""

from __future__ import annotations

import io
import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, SEVERITY_KEY, TIME_KEY, JsonLogFormatter, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, DATA_FIELD
from pipelex.tools.log.log_redaction import CYCLE_TEXT, REDACTED_TEXT
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator


def _package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def _own_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    """Every line this module emitted, each parsed as one JSON object, whatever else the process logged meanwhile."""
    lines = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
    return [line for line in lines if line[LOGGER_KEY] == __name__]


class TestJsonLogSink:
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

    def test_each_record_is_one_json_object_with_the_fixed_keys(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        before = datetime.now(tz=UTC)
        fresh.info("first")
        fresh.warning("second")

        first, second = _own_lines(buffer)
        assert first[MESSAGE_KEY] == "first"
        assert first[SEVERITY_KEY] == "INFO"
        assert first[LOGGER_KEY] == __name__
        assert second[MESSAGE_KEY] == "second"
        assert second[SEVERITY_KEY] == "WARNING"
        assert first[TIME_KEY].endswith("Z")
        stamped = datetime.fromisoformat(first[TIME_KEY])
        assert stamped >= before.replace(microsecond=(before.microsecond // 1000) * 1000)
        assert EXCEPTION_KEY not in first

    def test_fields_context_and_data_ride_flat_beside_the_fixed_keys(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        with fresh.context(request_id="r1", pipeline_run_id="p1"):
            fresh.info("scanned", fields={"files": 7, "ratio": 0.5, "ok": True, "tags": ["a", "b"]})
            fresh.info({"key": "value", "nested": {"flag": True}}, title="Config")

        scanned, structured = _own_lines(buffer)
        assert scanned["files"] == 7
        assert scanned["ratio"] == 0.5
        assert scanned["ok"] is True
        assert scanned["tags"] == ["a", "b"]
        assert scanned["request_id"] == "r1"
        assert scanned["pipeline_run_id"] == "p1"
        assert "pipe_run_id" not in scanned
        assert structured[DATA_FIELD] == {"key": "value", "nested": {"flag": True}}
        assert structured[MESSAGE_KEY].startswith("Config:")

    def test_a_field_value_carrying_a_newline_is_still_one_line_and_forges_nothing(self, json_log: tuple[Log, io.StringIO]) -> None:
        """Redaction neutralises the control characters in a field value before the sink writes it, so a caller cannot forge a line or a field."""
        fresh, buffer = json_log

        fresh.info("received", fields={"detail": 'ok\nseve\x1b[31mrity="ERROR"'})

        assert len([line for line in buffer.getvalue().splitlines() if "detail" in line]) == 1
        (received,) = _own_lines(buffer)
        assert received["detail"] == 'ok\\nseve\\x1b[31mrity="ERROR"'

    def test_the_exception_is_a_field_and_not_part_of_the_message(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("failed", include_exception=True)

        (line,) = _own_lines(buffer)
        assert line[MESSAGE_KEY] == "failed"
        assert "Traceback (most recent call last)" in line[EXCEPTION_KEY]
        assert "ValueError: boom" in line[EXCEPTION_KEY]

    def test_a_secret_in_an_exceptions_message_is_scrubbed_from_the_exception_value(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        try:
            msg = "refused: Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.body.sig for sk_live_0123456789abcdef"
            raise RuntimeError(msg)
        except RuntimeError:
            fresh.error("call failed", include_exception=True)

        (line,) = _own_lines(buffer)
        assert "eyJhbGciOiJIUzI1NiJ9" not in line[EXCEPTION_KEY]
        assert "sk_live_0123456789abcdef" not in line[EXCEPTION_KEY]
        assert line[EXCEPTION_KEY].endswith(f"RuntimeError: refused: Authorization: Bearer {REDACTED_TEXT} for sk_{REDACTED_TEXT}")

    def test_no_ansi_ever_even_for_a_warning_or_an_error(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        fresh.warning("careful")
        fresh.error("broken")
        fresh.critical("down")

        assert "\x1b" not in buffer.getvalue()
        assert [line[SEVERITY_KEY] for line in _own_lines(buffer)] == ["WARNING", "ERROR", "CRITICAL"]

    def test_a_field_named_like_a_fixed_key_is_prefixed_not_lost(self, json_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = json_log
        fresh.info("collide", fields={SEVERITY_KEY: "custom", TIME_KEY: "then", "logger": "other"})

        (line,) = _own_lines(buffer)
        assert line[SEVERITY_KEY] == "INFO"
        assert line[f"{COLLIDING_FIELD_PREFIX}{SEVERITY_KEY}"] == "custom"
        assert line[f"{COLLIDING_FIELD_PREFIX}{TIME_KEY}"] == "then"
        assert line[f"{COLLIDING_FIELD_PREFIX}logger"] == "other"

    def test_a_value_json_does_not_know_is_serialized_and_never_lost(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A model dumps in JSON mode, a datetime becomes text, a cycle is cut by the redaction walk and keeps the line an object."""

        class Item(BaseModel):
            name: str
            when: datetime

        cyclic: dict[str, Any] = {}
        cyclic["me"] = cyclic
        fresh, buffer = json_log
        fresh.info("odd values", fields={"item": Item(name="x", when=datetime(2020, 1, 2, tzinfo=UTC)), "when": datetime(2021, 3, 4, tzinfo=UTC)})
        fresh.info("cyclic value", fields={"loop": cyclic})

        odd, cyclic_line = _own_lines(buffer)
        assert odd["item"] == {"name": "x", "when": "2020-01-02T00:00:00Z"}
        assert odd["when"] == "2021-03-04 00:00:00+00:00"
        assert cyclic_line[MESSAGE_KEY] == "cyclic value"
        assert cyclic_line["loop"] == {"me": CYCLE_TEXT}

    def test_a_raw_cycle_reaching_the_formatter_keeps_the_line_an_object(self) -> None:
        """The sink's own guard, for a process with redaction off: a value ``json`` refuses is written as its ``repr``, the line stays one object."""
        cyclic: dict[str, Any] = {}
        cyclic["me"] = cyclic
        record = logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="cyclic value", args=(), exc_info=None)
        record.loop = cyclic

        line = json.loads(JsonLogFormatter().format(record))

        assert line[MESSAGE_KEY] == "cyclic value"
        assert isinstance(line["loop"], str)
        assert "{...}" in line["loop"]

    def test_a_non_finite_float_is_written_as_text_a_strict_parser_accepts(self, json_log: tuple[Log, io.StringIO]) -> None:
        """JSON has no NaN: the bare tokens Python writes by default would cost the whole line, so they are strings."""

        def refuse(token: str) -> None:
            msg = f"bare token {token} on the wire"
            raise ValueError(msg)

        fresh, buffer = json_log
        fresh.info(
            "readings", fields={"reading": float("nan"), "up": float("inf"), "nested": {"deep": [float("-inf"), 1]}, "ok": "kept", "flag": True}
        )
        fresh.info({"structured": float("inf")}, title="Data")

        strict = [json.loads(line, parse_constant=refuse) for line in buffer.getvalue().splitlines() if line]
        readings, structured = [line for line in strict if line[LOGGER_KEY] == __name__]
        assert readings["reading"] == "NaN"
        assert readings["up"] == "Infinity"
        assert readings["nested"] == {"deep": ["-Infinity", 1]}
        assert readings["ok"] == "kept"
        assert readings["flag"] is True
        assert structured[DATA_FIELD] == {"structured": "Infinity"}

    def test_the_sinks_own_keys_are_reserved_with_or_without_an_exception(self, json_log: tuple[Log, io.StringIO]) -> None:
        """A field's wire name must not depend on an exception being active, and a cycle under a reserved name must not cost the line."""
        cyclic: dict[str, Any] = {}
        cyclic["me"] = cyclic
        fresh, buffer = json_log
        fresh.info("no exception", fields={EXCEPTION_KEY: "supplied"})
        try:
            msg = "boom"
            raise ValueError(msg)
        except ValueError:
            fresh.error("with exception", include_exception=True, fields={EXCEPTION_KEY: "supplied"})
        fresh.info("cycle under a reserved name", fields={EXCEPTION_KEY: cyclic})

        without, with_exception, cycle = _own_lines(buffer)
        assert EXCEPTION_KEY not in without
        assert without[f"{COLLIDING_FIELD_PREFIX}{EXCEPTION_KEY}"] == "supplied"
        assert "ValueError: boom" in with_exception[EXCEPTION_KEY]
        assert with_exception[f"{COLLIDING_FIELD_PREFIX}{EXCEPTION_KEY}"] == "supplied"
        assert cycle[MESSAGE_KEY] == "cycle under a reserved name"
        assert cycle[f"{COLLIDING_FIELD_PREFIX}{EXCEPTION_KEY}"] == {"me": CYCLE_TEXT}

    def test_redirect_to_stderr_moves_the_stream(self, json_log: tuple[Log, io.StringIO], capsys: pytest.CaptureFixture[str]) -> None:
        fresh, buffer = json_log
        fresh.redirect_to_stderr()
        fresh.info("on stderr now")

        assert _own_lines(buffer) == []
        captured = capsys.readouterr()
        assert any(json.loads(line)[MESSAGE_KEY] == "on stderr now" for line in captured.err.splitlines() if line.startswith("{"))
        assert fresh.sink is not None
        assert isinstance(fresh.sink, JsonLogSink)
        assert fresh.sink.handler.stream is sys.stderr  # type: ignore[attr-defined]

    def test_content_the_serialization_refuses_is_redacted_by_name_before_it_falls_back_to_a_repr(self, json_log: tuple[Log, io.StringIO]) -> None:
        """The ``repr`` of an entry holding an object is beyond what the string families read back out of text."""
        fresh, buffer = json_log
        cyclic: dict[str, Any] = {"password": {"value": "private_credential_12345"}}
        cyclic["self"] = cyclic

        fresh.info(cyclic)

        (line,) = _own_lines(buffer)
        assert "private_credential_12345" not in line[MESSAGE_KEY]
        assert REDACTED_TEXT in line[MESSAGE_KEY]

    def test_a_caller_field_named_like_the_content_attribute_is_carried_under_the_collision_prefix(self, json_log: tuple[Log, io.StringIO]) -> None:
        """``data`` is the runtime's own rendering and keeps its control characters; a caller's string must not land there."""
        fresh, buffer = json_log

        fresh.info("string content", fields={DATA_FIELD: "ok\nFAKE LINE", "other": "ok\nFAKE LINE"})

        (line,) = _own_lines(buffer)
        assert DATA_FIELD not in line
        assert line[f"{COLLIDING_FIELD_PREFIX}{DATA_FIELD}"] == "ok\\nFAKE LINE"
        assert line["other"] == "ok\\nFAKE LINE"
