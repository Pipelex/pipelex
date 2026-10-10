"""The ``console`` sink renders byte for byte what a plain Rich handler renders, plus the fields and another library's name.

The reference is a plain ``RichHandler`` fed every ``[runtime.log.rich_log]`` setting, reading no message as
markup as the console does, with the stdlib's plain formatter. Both handlers are pointed at the same kind of
non-terminal console and handed the same fixed record set. A Pipelex record whose call gave no field renders
identically through both; a record with fields renders the same line with the fields after the message, and a
record from another library the same line with that library's package name before it.
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
from pipelex.tools.log.console_fields import ADVICE_STYLE, one_line_text
from pipelex.tools.log.console_layouts import LogLayout
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log_config import HighlighterName, LogConfig, RichLogConfig
from pipelex.tools.log.log_fields import RICH_MARKUP_ATTRIBUTE, USER_ACTION_FIELD, attach_log_record_extra
from pipelex.tools.log.log_redaction import CYCLE_TEXT
from pipelex.tools.misc.toml_utils import load_toml_from_path
from tests.helpers.console_log_rendering import (
    PIPE_RUN_FIELDS,
    console_sink_on_buffer,
    installed_log,
    package_rich_log_config_without_rich_tracebacks,
    record_with_fields,
    rendered_text,
    styles_of,
)

CONSOLE_WIDTH = 100


def _package_rich_log_config() -> RichLogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"]).rich_log


def _reference_handler(*, config: RichLogConfig) -> logging.Handler:
    """A plain Rich handler with the sink's settings, setting for setting, reading no message as markup."""
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
        show_path=config.is_show_path,
        enable_link_path=config.is_link_path_enabled,
        highlighter=highlighter,
        markup=False,
        rich_tracebacks=config.is_rich_tracebacks,
        tracebacks_word_wrap=config.is_tracebacks_word_wrap,
        tracebacks_show_locals=config.is_tracebacks_show_locals,
        tracebacks_suppress=config.tracebacks_suppress,
        keywords=config.keywords_to_hilight,
    )
    handler.setFormatter(logging.Formatter())
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
    record(name="myapp.jobs.nightly", level=logging.INFO, message="A line from an application")
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


def _with_package_names(*, reference: str) -> str:
    """The reference rendering with each foreign line's package name before its message, taking the padding after it."""
    for package_name, message in (("openai", "Retrying request"), ("myapp", "A line from an application")):
        prefix = f"{package_name}: "
        assert f"{message}{' ' * len(prefix)}" in reference
        reference = reference.replace(f"{message}{' ' * len(prefix)}", f"{prefix}{message}")
    return reference


class TestConsoleLogSink:
    @pytest.mark.parametrize("is_rich_tracebacks", [True, False], ids=["rich tracebacks", "tracebacks as text"])
    def test_output_is_byte_identical_to_a_plain_rich_handler_when_no_call_gave_a_field(self, is_rich_tracebacks: bool) -> None:
        """The run identifier and the structured content's ``data`` are attached too, and neither adds anything to the line.

        A Pipelex line carries no prefix, and a line from another library its package name alone, which takes the
        padding the message column had after the message. With Rich tracebacks off, the traceback reaches the
        handler as text after the message, which the sink splits off and prints under the line: a traceback with
        nothing Rich would read as markup prints as it did.
        """
        config = _package_rich_log_config().model_copy(update={"is_rich_tracebacks": is_rich_tracebacks})
        reference = _render(_reference_handler(config=config), is_with_call_fields=False)
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler, is_with_call_fields=False)

        assert rendered
        assert "INFO     Running the pipe" in rendered
        assert "myapp: A line from an application" in rendered
        assert "ValueError" in rendered
        assert rendered == _with_package_names(reference=reference)

    def test_a_record_with_fields_gets_them_after_the_message_and_every_other_line_is_unchanged(self) -> None:
        config = _package_rich_log_config()
        reference = _render(_reference_handler(config=config))
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler)

        assert "WARNING  Slow backend files=7" in rendered
        assert "r1" not in rendered
        # The suffix takes the padding the message column had after the message, so the line keeps its width.
        suffix = " files=7"
        expected = reference.replace(f"Slow backend{' ' * len(suffix)}", f"Slow backend{suffix}")
        assert rendered == _with_package_names(reference=expected)

    def test_the_package_name_stays_on_a_line_that_carries_a_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        """The Rich handler renders such a line from ``formatMessage`` alone, and the package name must survive that path too."""
        config = _package_rich_log_config()
        assert config.is_rich_tracebacks, "the shipped default is what the regression rode on"
        caplog.set_level(logging.INFO, logger="myapp.jobs.nightly")
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)):
            try:
                msg = "boom"
                raise ValueError(msg)
            except ValueError:
                logging.getLogger("myapp.jobs.nightly").exception("Failed")

        rendered = buffer.getvalue()
        assert "myapp: Failed" in rendered
        assert "ValueError: boom" in rendered

    @pytest.mark.parametrize(
        "logger_name",
        ["pipelex.pipe_operators.pipe_llm", "pipelex_api.security", "pipelex_temporal.worker", "root"],
        ids=["the runtime", "the API server", "a Pipelex plugin", "the root logger"],
    )
    def test_a_pipelex_line_and_a_root_line_carry_no_prefix(self, logger_name: str) -> None:
        text = rendered_text(record=record_with_fields(message="Loaded the library", logger_name=logger_name))

        assert text.plain == "Loaded the library"

    def test_a_line_from_another_library_starts_with_its_package_name_dimmed(self) -> None:
        text = rendered_text(record=record_with_fields(message="HTTP Request: POST", logger_name="httpx._client", extra={"attempt": 2}))

        assert text.plain == "httpx: HTTP Request: POST attempt=2"
        assert "dim" in styles_of(text=text, fragment="httpx: ")

    @pytest.mark.parametrize("is_show_path", [False, True], ids=["the default", "is_show_path"])
    def test_the_source_path_column_shows_only_when_the_setting_asks_for_it(self, is_show_path: bool) -> None:
        config = _package_rich_log_config().model_copy(update={"is_show_path": is_show_path, "is_link_path_enabled": False})
        sink = ConsoleLogSink(rich_log_config=config, target=ConsoleTarget.STDERR)

        rendered = _render(sink.handler)

        assert ("module.py:42" in rendered) is is_show_path

    def test_the_shipped_default_hides_the_source_path_column(self) -> None:
        assert _package_rich_log_config().is_show_path is False

    def test_the_advice_prints_on_a_line_of_its_own_under_the_record_and_never_in_the_suffix(self) -> None:
        text = rendered_text(
            record=record_with_fields(message="A configuration file is out of date", extra={"file.path": "pipelex.toml", USER_ACTION_FIELD: "Run pipelex migrate"})
        )

        assert text.plain == "A configuration file is out of date file.path=pipelex.toml\n→ Run pipelex migrate"
        assert ADVICE_STYLE in styles_of(text=text, fragment="\n→ Run pipelex migrate")

    def test_the_advice_is_written_whole_and_on_one_line(self) -> None:
        advice = "Run pipelex migrate " + "then check the file " * 10 + "\x1b[31mred"

        text = rendered_text(record=record_with_fields(message="A configuration file is out of date", extra={USER_ACTION_FIELD: advice}))

        (advice_line,) = text.plain.splitlines()[1:]
        assert advice_line == f"→ {one_line_text(text=advice)}"
        assert "\x1b" not in text.plain

    def test_with_tracebacks_as_text_the_advice_comes_before_the_traceback(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        sink = console_sink_on_buffer(buffer=buffer, rich_log_config=package_rich_log_config_without_rich_tracebacks())
        with installed_log(sink=sink) as fresh:
            try:
                msg = "boom"
                raise ValueError(msg)
            except ValueError:
                fresh.error("Pipe run failed", include_exception=True, fields={"attempt": 2, USER_ACTION_FIELD: "Check the backend"})

        lines = buffer.getvalue().splitlines()
        (index_line,) = [index for index, line in enumerate(lines) if "Pipe run failed attempt=2" in line]
        assert lines[index_line + 1].strip() == "→ Check the backend"
        assert any("Traceback (most recent call last):" in line for line in lines[index_line + 2 :])

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
        ("layout", "fields"),
        [
            (None, {"files": 7}),
            (LogLayout.PIPE_RUN, {**PIPE_RUN_FIELDS, "files": 7}),
        ],
        ids=["the message", "a layout"],
    )
    def test_with_tracebacks_as_text_a_message_ending_in_a_line_break_still_has_its_traceback_start_a_line(
        self,
        caplog: pytest.LogCaptureFixture,
        layout: LogLayout | None,
        fields: dict[str, Any],
    ) -> None:
        """The formatter adds a line break before the exception text only when the message lacks one, so it ran on straight after the suffix."""
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        sink = console_sink_on_buffer(buffer=buffer, rich_log_config=package_rich_log_config_without_rich_tracebacks())
        with installed_log(sink=sink) as fresh:
            try:
                msg = "boom"
                raise ValueError(msg)
            except ValueError:
                fresh.error("Pipe run failed\n", include_exception=True, fields=fields, layout=layout)

        lines = buffer.getvalue().splitlines()
        (suffix_line,) = [line for line in lines if "files=7" in line]
        assert "Traceback" not in suffix_line
        assert any(line.strip() == "Traceback (most recent call last):" for line in lines)

    @pytest.mark.parametrize(
        "message",
        [
            "expected list[int], got str",
            "Expected list[int], got [red]str[/red]",
            "no such file: [/etc/pipelex.toml]",
            "[bold]not a style[/bold] :fire:",
        ],
        ids=["a type complaint", "a type complaint carrying a style tag", "a bracketed path", "a style tag and an emoji code"],
    )
    def test_a_message_shaped_like_markup_prints_exactly_as_written(self, message: str) -> None:
        """An error message carries text nobody chose, and Rich read a tag-shaped span in it as markup.

        Rich's tag starts with a lowercase letter, `#`, `/` or `@`, so `list[int]` lost its bracketed span, a
        style tag coloured what it wrapped and vanished, and a bracketed path opened what Rich reads as a
        closing tag and raised inside the handler, costing the whole line. The console reads no message as
        markup, so each prints as written, an emoji code included.
        """
        rendered = _render_one(config=_package_rich_log_config(), message=message, extra=None)

        assert message in rendered

    def test_a_logger_named_in_lowercase_keeps_its_package_name(self, caplog: pytest.LogCaptureFixture) -> None:
        """A prefix written into the message as ``[name]: `` was read by Rich as a tag and removed when the name started lowercase.

        The line printed as ``: Pipe run failed``, with nothing saying which library wrote it. The package name is
        styled text of its own, never markup, so it prints whatever it is spelled like.
        """
        caplog.set_level(logging.INFO, logger="myapp.jobs.nightly")
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)):
            logging.getLogger("myapp.jobs.nightly").error("Pipe run failed")

        assert "myapp: Pipe run failed" in buffer.getvalue()

    def test_a_circular_content_prints_its_cycle_marker(self, caplog: pytest.LogCaptureFixture) -> None:
        """A content JSON refuses is rendered as its ``repr``, where the redaction cuts the cycle with ``[cycle]``.

        Read as markup, the marker was a tag Rich removed, so the line printed ``'self': ''``.
        """
        caplog.set_level(logging.INFO, logger=__name__)
        circular: dict[str, Any] = {"the_content_key": 1}
        circular["self"] = circular
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            fresh.info(circular)

        assert f"{{'the_content_key': 1, 'self': '{CYCLE_TEXT}'}}" in buffer.getvalue()

    def test_a_line_rich_refuses_costs_its_rendering_and_never_the_log_call(self) -> None:
        """Rich overrides ``emit`` without the stdlib's ``handleError`` guard, so a refusal left the log call.

        No Pipelex message is read as markup, but Rich still honours its own per-record ``markup`` attribute,
        which a third-party library may stamp on its record: a bracketed path in such a line reads as a closing
        tag with nothing open, and Rich raises ``MarkupError`` from inside the handler. Unguarded, that
        propagated out of the call that logged it and replaced whatever was being reported with itself. The
        sink's handler restores the guard, so the worst a line Rich refuses costs is its own rendering.
        """
        message = "no such file: [/etc/pipelex.toml]"

        rendered = _render_one(config=_package_rich_log_config(), message=message, extra={RICH_MARKUP_ATTRIBUTE: True})

        assert message not in rendered

    def test_the_handler_is_a_rich_handler_with_the_plain_formatter_and_the_same_object_on_every_read(self) -> None:
        sink = ConsoleLogSink(rich_log_config=_package_rich_log_config(), target=ConsoleTarget.STDERR)

        handler = sink.handler

        assert isinstance(handler, RichHandler)
        assert type(handler.formatter) is logging.Formatter
        assert sink.handler is handler
