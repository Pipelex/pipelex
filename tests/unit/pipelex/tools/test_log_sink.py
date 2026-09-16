"""The sink base: the processor slot runs before the handler formats, the handler is built once, and a stream is resolved at call time."""

from __future__ import annotations

import io
import logging
import sys
from typing import TYPE_CHECKING

import pytest
from typing_extensions import override

from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.log_sink import LogSink, render_json, spell_non_finite, stream_for_target

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class _RecordingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.seen: list[str] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.seen.append(f"{record.getMessage()}|{getattr(record, 'redacted', '-')}")


class _RecordingSink(LogSink):
    def __init__(self) -> None:
        super().__init__()
        self.built = 0

    @override
    def make_handler(self) -> logging.Handler:
        self.built += 1
        return _RecordingHandler()


def _record(*, message: str) -> logging.LogRecord:
    return logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg=message, args=(), exc_info=None)


class TestLogSink:
    def test_the_handler_is_built_once_and_the_processors_run_before_it_emits(self) -> None:
        sink = _RecordingSink()

        def redact(record: logging.LogRecord) -> None:
            record.redacted = "yes"

        sink.processors.append(redact)
        handler = sink.handler
        handler.handle(_record(message="one"))
        sink.handler.handle(_record(message="two"))

        assert sink.built == 1
        assert sink.handler is handler
        assert isinstance(handler, _RecordingHandler)
        assert handler.seen == ["one|yes", "two|yes"]

    def test_a_processor_that_raises_costs_that_records_processing_and_not_the_log_call(self, mocker: MockerFixture) -> None:
        """The stdlib runs a handler's filters outside any ``try``, so an unguarded processor would raise out of ``log.info``."""
        sink = _RecordingSink()

        def fail(_record: logging.LogRecord) -> None:
            msg = "this processor is broken"
            raise RuntimeError(msg)

        def redact(record: logging.LogRecord) -> None:
            record.redacted = "yes"

        sink.processors.extend([fail, redact])
        handler = sink.handler
        handle_error = mocker.patch.object(handler, "handleError")

        handler.handle(_record(message="one"))

        assert isinstance(handler, _RecordingHandler)
        assert handler.seen == ["one|yes"]
        assert handle_error.call_count == 1

    def test_redirect_to_stderr_is_a_no_op_on_a_sink_that_writes_to_no_stream(self) -> None:
        sink = _RecordingSink()
        sink.redirect_to_stderr()
        assert sink.built == 0

    def test_stream_for_target_resolves_the_live_process_stream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        replaced_err = io.StringIO()
        monkeypatch.setattr(sys, "stderr", replaced_err)

        assert stream_for_target(target=ConsoleTarget.STDERR) is replaced_err
        assert stream_for_target(target=ConsoleTarget.STDOUT) is sys.stdout
        with pytest.raises(ValueError, match="file"):
            stream_for_target(target=ConsoleTarget.FILE)

    def test_render_json_never_raises(self) -> None:
        cyclic: dict[str, object] = {}
        cyclic["me"] = cyclic

        assert render_json(value={"a": 1}) == '{"a": 1}'
        assert render_json(value=object()).startswith('"<object object at')
        assert "{...}" in render_json(value=cyclic)
        assert render_json(value={(1, 2): "a"}) == "\"{(1, 2): 'a'}\""

    def test_a_non_finite_float_is_spelled_as_text_at_any_depth_and_nothing_else_moves(self) -> None:
        value = {"nan": float("nan"), "inf": float("inf"), "deep": [float("-inf"), 1, True, "x"], "pair": (2.5, float("nan"))}

        spelled = spell_non_finite(value=value)

        assert spelled == {"nan": "NaN", "inf": "Infinity", "deep": ["-Infinity", 1, True, "x"], "pair": [2.5, "NaN"]}
        assert spelled["deep"][2] is True
        assert render_json(value=[float("nan")]) == '["NaN"]'
        assert "NaN" not in render_json(value=[1.5])
