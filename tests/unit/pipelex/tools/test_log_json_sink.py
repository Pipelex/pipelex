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
from pipelex.tools.log.json_log_sink import EXCEPTION_KEY, LOGGER_KEY, MESSAGE_KEY, SEVERITY_KEY, TIME_KEY, JsonLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig
from pipelex.tools.log.log_fields import COLLIDING_FIELD_PREFIX, DATA_FIELD
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
        """A model dumps in JSON mode, a datetime becomes text, a cycle keeps the line an object."""

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
        assert isinstance(cyclic_line["loop"], str)
        assert "{...}" in cyclic_line["loop"]

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
