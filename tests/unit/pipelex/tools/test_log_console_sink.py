"""The ``console`` sink renders byte for byte what the Rich handler rendered before it existed, plus the fields.

The reference is the handler ``log.configure`` used to build inline: a ``RichHandler`` fed every
``[runtime.log.rich_log]`` setting and the emoji formatter. Both handlers are pointed at the same kind
of non-terminal console and handed the same fixed record set. A record whose call gave no field renders
identically through both; a record with fields renders the same line with the fields after the message.
"""

from __future__ import annotations

import io
import logging
from typing import Any

import pytest
from rich.console import Console
from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
from rich.logging import RichHandler

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log_config import HighlighterName, LogConfig, RichLogConfig
from pipelex.tools.log.log_fields import VERBATIM_MARK, attach_log_record_extra
from pipelex.tools.log.log_formatter import EmojiLogFormatter
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.helpers.console_log_rendering import (
    PIPE_RUN_FIELDS,
    console_sink_on_buffer,
    installed_log,
    package_rich_log_config_without_rich_tracebacks,
)

CONSOLE_WIDTH = 100


def _package_rich_log_config() -> RichLogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"]).rich_log


def _reference_handler(*, config: RichLogConfig) -> logging.Handler:
    """The handler ``log.configure`` built before the sink seam, setting for setting."""
    highlighter: Highlighter
    match config.highlighter_name:
        case HighlighterName.JSON:
            highlighter = JSONHighlighter()
        case HighlighterName.REPR:
            highlighter = ReprHighlighter()
    handler = RichHandler(
        console=Console(file=io.StringIO()),
        show_time=config.is_show_time,
        show_level=config.is_show_level,
        enable_link_path=config.is_link_path_enabled,
        highlighter=highlighter,
        markup=config.is_markup_enabled,
        rich_tracebacks=config.is_rich_tracebacks,
        tracebacks_word_wrap=config.is_tracebacks_word_wrap,
        tracebacks_show_locals=config.is_tracebacks_show_locals,
        tracebacks_suppress=config.tracebacks_suppress,
        keywords=config.keywords_to_hilight,
    )
    handler.setFormatter(EmojiLogFormatter())
    return handler


def _fixed_record_set(*, is_with_call_fields: bool = True) -> list[logging.LogRecord]:
    """Every shape a record takes: a bare line, a warning with fields, structured content, an error with a traceback, a foreign logger.

    Without call fields, the warning carries the run identifier alone, which the console never shows.
    """
    records: list[logging.LogRecord] = []
    warning_extra: dict[str, Any] = {"files": 7, "request_id": "r1"} if is_with_call_fields else {"request_id": "r1"}

    def record(*, name: str, level: int, message: str, exc_info: Any = None, extra: dict[str, Any] | None = None) -> None:
        built = logging.LogRecord(name=name, level=level, pathname="/repo/pipelex/module.py", lineno=42, msg=message, args=(), exc_info=exc_info)
        built.created = 1_700_000_000.0
        built.msecs = 0.0
        if extra:
            attach_log_record_extra(record=built, extra=extra)
        records.append(built)

    record(name="pipelex.pipe_operators.pipe_llm", level=logging.INFO, message="Running the pipe")
    record(name="pipelex.pipe_operators.pipe_llm", level=logging.WARNING, message="Slow backend", extra=warning_extra)
    record(name="pipelex.pipeline.pipe_run", level=logging.INFO, message='Config:\n{\n    "key": "value"\n}', extra={"data": {"key": "value"}})
    try:
        msg = "boom"
        raise ValueError(msg)
    except ValueError as exc:
        record(name="pipelex.pipeline.pipe_run", level=logging.ERROR, message="Failed", exc_info=(type(exc), exc, exc.__traceback__))
    record(name="openai._base_client", level=logging.INFO, message="Retrying request")
    record(name="myapp.jobs.nightly", level=logging.INFO, message="A logger with no emoji")
    return records


def _render_one(*, config: RichLogConfig, message: str, extra: dict[str, Any] | None) -> str:
    """One record through a fresh console sink, so a per-record attribute can be read off the rendering."""
    buffer = io.StringIO()
    handler = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR).handler
    assert isinstance(handler, RichHandler)
    handler.console = Console(file=buffer, width=CONSOLE_WIDTH, force_terminal=False, color_system=None, legacy_windows=False)
    record = logging.LogRecord(
        name="pipelex.system.exceptions", level=logging.ERROR, pathname="/repo/pipelex/module.py", lineno=42, msg=message, args=(), exc_info=None
    )
    for name, value in (extra or {}).items():
        setattr(record, name, value)
    handler.handle(record)
    return buffer.getvalue()


def _render(handler: logging.Handler, *, is_with_call_fields: bool = True) -> str:
    buffer = io.StringIO()
    rich_handler = handler
    assert isinstance(rich_handler, RichHandler)
    rich_handler.console = Console(file=buffer, width=CONSOLE_WIDTH, force_terminal=False, color_system=None, legacy_windows=False)
    for record in _fixed_record_set(is_with_call_fields=is_with_call_fields):
        handler.handle(record)
    return buffer.getvalue()


class TestConsoleLogSink:
    @pytest.mark.parametrize("is_rich_tracebacks", [True, False], ids=["rich tracebacks", "tracebacks as text"])
    def test_output_is_byte_identical_to_the_handler_configure_used_to_build_when_no_call_gave_a_field(self, is_rich_tracebacks: bool) -> None:
        """The run identifier and the structured content's ``data`` are attached too, and neither adds anything to the line.

        With Rich tracebacks off, the traceback reaches the handler as text after the message, which the sink
        splits off and prints under the line: a traceback with nothing Rich would read as markup prints as it did.
        """
        config = _package_rich_log_config().model_copy(update={"is_rich_tracebacks": is_rich_tracebacks})
        reference = _render(_reference_handler(config=config), is_with_call_fields=False)
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler, is_with_call_fields=False)

        assert rendered
        assert "🧠: Running the pipe" in rendered
        assert "ValueError" in rendered
        assert rendered == reference

    def test_a_record_with_fields_gets_them_after_the_message_and_every_other_line_is_unchanged(self) -> None:
        config = _package_rich_log_config()
        reference = _render(_reference_handler(config=config))
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler)

        assert "🧠: Slow backend files=7" in rendered
        assert "r1" not in rendered
        # The suffix takes the padding the message column had after the message, so the line keeps its width.
        suffix = " files=7"
        assert rendered == reference.replace(f"🧠: Slow backend{' ' * len(suffix)}", f"🧠: Slow backend{suffix}")

    def test_the_prefix_stays_on_a_line_that_carries_a_traceback(self) -> None:
        """The Rich handler renders such a line from ``formatMessage`` alone, and the emoji must survive that path too."""
        config = _package_rich_log_config()
        assert config.is_rich_tracebacks, "the shipped default is what the regression rode on"
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler)

        assert "🧠: Failed" in rendered
        assert "ValueError: boom" in rendered

    @pytest.mark.parametrize(
        ("layout", "fields", "expected_line"),
        [
            (None, {"attempt": 2}, "Pipe run failed attempt=2"),
            (LogLayout.PIPE_RUN, {**PIPE_RUN_FIELDS, "attempt": 2}, "PipeCompose: compose_company → Company attempt=2"),
        ],
        ids=["the message", "a layout"],
    )
    def test_with_tracebacks_as_text_the_fields_stay_on_the_line_and_the_traceback_prints_under_it(
        self,
        caplog: pytest.LogCaptureFixture,
        layout: LogLayout | None,
        fields: dict[str, Any],
        expected_line: str,
    ) -> None:
        """With Rich tracebacks off, the formatter appends the traceback to the message the handler receives.

        The suffix used to follow that text, so the fields read as part of the exception, and a layout, which
        replaces the message, dropped the traceback whole. The exception's message is shaped like markup,
        which the traceback text must never be read as.
        """
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        sink = console_sink_on_buffer(buffer=buffer, rich_log_config=package_rich_log_config_without_rich_tracebacks())
        with installed_log(sink=sink) as fresh:
            try:
                msg = "no such file: [/etc/pipelex.toml]"
                raise ValueError(msg)
            except ValueError:
                fresh.error("Pipe run failed", include_exception=True, fields=fields, layout=layout)

        lines = buffer.getvalue().splitlines()
        (index_line,) = [index_candidate for index_candidate, line in enumerate(lines) if expected_line in line]
        lines_under = lines[index_line + 1 :]
        assert any("Traceback (most recent call last):" in line for line in lines_under)
        assert any("ValueError: no such file: [/etc/pipelex.toml]" in line for line in lines_under)
        assert not any("attempt=" in line for line in lines_under)

    @pytest.mark.parametrize(
        "message",
        [
            "expected list[int], got str",
            "no such file: [/etc/pipelex.toml]",
        ],
        ids=["a type complaint", "a bracketed path"],
    )
    def test_a_message_shaped_like_markup_renders_intact_only_when_the_record_asks_for_verbatim(self, message: str) -> None:
        """An error message carries text nobody chose, and Rich reads a tag-shaped span in it as markup.

        Rich's tag has to start with a lowercase letter, `#`, `/` or `@`, so `[Errno 2]` is safe and the
        two shapes this codebase's messages are actually made of are not: `list[int]` loses the bracketed
        span, and a bracketed path opens what Rich reads as a closing tag and raises inside the handler,
        where `handleError` costs the whole line. The configuration asks for markup and Pipelex's own
        lines use it, so the opt-out is per record: Rich reads `markup` off the record ahead of its
        handler's setting, which is what `TracebackMessageError` stamps through `VERBATIM_MARK`.
        """
        config = _package_rich_log_config()
        assert config.is_markup_enabled, "the mark is an opt-out, so an enabled setting is what it opts out of"

        interpreted = _render_one(config=config, message=message, extra=None)
        verbatim = _render_one(config=config, message=message, extra={VERBATIM_MARK: False})

        assert message not in interpreted
        assert message in verbatim

    @pytest.mark.parametrize(
        "message",
        [
            "expected list[int], got str",
            "no such file: [/etc/pipelex.toml]",
        ],
        ids=["a type complaint", "a bracketed path"],
    )
    def test_a_message_rich_refuses_costs_its_rendering_and_never_the_log_call(self, message: str) -> None:
        """Rich overrides ``emit`` without the stdlib's ``handleError`` guard, so a refusal left the log call.

        A bracketed path reads as a closing tag with nothing open and Rich raises ``MarkupError`` from
        inside the handler: unguarded, that propagated out of `log.error` and replaced the failure being
        reported with itself. The sink's handler restores the guard, so the worst a line Rich refuses costs
        is its own rendering.
        """
        config = _package_rich_log_config()

        rendered = _render_one(config=config, message=message, extra=None)

        assert message not in rendered

    def test_the_handler_is_a_rich_handler_with_the_emoji_formatter_and_the_same_object_on_every_read(self) -> None:
        sink = ConsoleLogSink(rich_log_config=_package_rich_log_config(), target=ConsoleTarget.STDERR)

        handler = sink.handler

        assert isinstance(handler, RichHandler)
        assert isinstance(handler.formatter, EmojiLogFormatter)
        assert sink.handler is handler
