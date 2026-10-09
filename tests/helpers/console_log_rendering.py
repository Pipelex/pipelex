"""Builders and readings shared by the tests of the console sink's field suffix, style map and layouts."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.logging import RichHandler
from rich.text import Text

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.system.console_target import ConsoleTarget
from pipelex.tools.log.console_log_sink import ConsoleLogSink
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig, RichLogConfig
from pipelex.tools.log.log_fields import LAYOUT_MARK, attach_log_record_extra
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    import io
    from collections.abc import Generator

    from pipelex.tools.log.console_layouts import LogLayout
    from pipelex.tools.log.log_sink import LogSink

CONSOLE_WIDTH = 200

# The fields the pipe-run layout presents, for a top-level run.
PIPE_RUN_FIELDS: dict[str, Any] = {
    "pipe_type": "PipeCompose",
    "pipe_code": "compose_company",
    "output_concept": "Company",
    "pipe_depth": 0,
}


def package_log_config() -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    return LogConfig.model_validate(config_dict["runtime"]["log"])


def console_handler() -> RichHandler:
    handler = ConsoleLogSink(rich_log_config=package_log_config().rich_log, target=ConsoleTarget.STDERR).handler
    assert isinstance(handler, RichHandler)
    return handler


def record_with_fields(*, message: str, extra: dict[str, Any] | None = None, layout: LogLayout | str | None = None) -> logging.LogRecord:
    """A record as the dispatch builds it: the extra attached through the fields channel, the layout under its mark."""
    record = logging.LogRecord(
        name="pipelex.tools.demo", level=logging.INFO, pathname="/repo/pipelex/module.py", lineno=42, msg=message, args=(), exc_info=None
    )
    attach_log_record_extra(record=record, extra=extra or {})
    if layout is not None:
        record.__dict__[LAYOUT_MARK] = layout
    return record


def rendered_text(*, record: logging.LogRecord) -> Text:
    """The ``Text`` the console sink's handler renders for the record's message line, styles and all."""
    handler = console_handler()
    record.message = record.getMessage()
    assert handler.formatter is not None
    rendered = handler.render_message(record, handler.formatter.formatMessage(record))
    assert isinstance(rendered, Text)
    return rendered


def styles_of(*, text: Text, fragment: str) -> list[str]:
    """The styles of the spans covering exactly the fragment, where it first appears in the text."""
    start = text.plain.index(fragment)
    end = start + len(fragment)
    return [str(span.style) for span in text.spans if span.start == start and span.end == end]


@contextmanager
def installed_log(*, sink: LogSink) -> Generator[Log]:
    """A fresh ``Log`` with the sink installed, reset afterwards so the root logger is left as found."""
    fresh = Log()
    fresh.configure(log_config=package_log_config())
    fresh.install_sink(sink)
    try:
        yield fresh
    finally:
        fresh.reset()


def package_rich_log_config_without_rich_tracebacks() -> RichLogConfig:
    """The package's console settings with Rich tracebacks off, so a traceback reaches the handler as text after the message."""
    return package_log_config().rich_log.model_copy(update={"is_rich_tracebacks": False})


def console_sink_on_buffer(*, buffer: io.StringIO, rich_log_config: RichLogConfig | None = None) -> ConsoleLogSink:
    """A console sink whose handler writes to the buffer, wide and colourless, so a line is read as plain text.

    The handler takes the package's console settings unless others are given.
    """
    sink = ConsoleLogSink(rich_log_config=rich_log_config or package_log_config().rich_log, target=ConsoleTarget.STDERR)
    handler = sink.handler
    assert isinstance(handler, RichHandler)
    handler.console = Console(file=buffer, width=CONSOLE_WIDTH, force_terminal=False, color_system=None, legacy_windows=False)
    return sink
