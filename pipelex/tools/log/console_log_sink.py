"""The ``console`` sink: the Rich handler with the emoji formatter and every ``[runtime.log.rich_log]`` setting.

The handler renders a record's fields after its message as a styled ``key=value`` suffix, and a record that
names a layout through that layout's template; what is shown and how it is coloured is in
``console_fields`` and ``console_layouts``. A traceback printed as text, with Rich tracebacks off, goes
under the line, after the suffix.

Rich is the ``cli`` extra. It is imported when the handler is built and nowhere else in this module, so
this module asks for Rich only where this sink is the one selected; a process that selects another sink
never reaches that import. One that selects this sink without Rich installed fails at boot with the extra
to install and the ``json`` alternative named, per the plugin system's fail-at-use rule.

Note that selecting another sink does not leave the process without Rich loaded: ``typer`` and
``instructor`` are core dependencies that require it, so an ``import pipelex`` loads Rich whatever this
module does. What is true is that nothing here is the reason.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.tools.log.console_fields import attached_fields, field_suffix_segments
from pipelex.tools.log.console_layouts import console_layout
from pipelex.tools.log.log_config import HighlighterName
from pipelex.tools.log.log_fields import LAYOUT_MARK
from pipelex.tools.log.log_formatter import EmojiLogFormatter, channel_prefix
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod, stream_for_target
from pipelex.tools.misc.rich_extra import require_rich

if TYPE_CHECKING:
    import logging

    from rich.console import ConsoleRenderable
    from rich.logging import RichHandler

    from pipelex.system.console_target import ConsoleTarget
    from pipelex.tools.log.log_config import RichLogConfig

#: What this sink says when the extra is missing, named once for every place in it that asks for Rich.
CONSOLE_SINK_MISSING_MESSAGE = (
    f"The '{LogSinkMethod.CONSOLE}' log sink renders through Rich. Install the extra, "
    f"or select the '{LogSinkMethod.JSON}' sink in [runtime.log] for a process with no terminal."
)


class ConsoleLogSink(LogSink):
    """A ``RichHandler`` on the configured stream, rendering the message, or its layout, and the fields after it."""

    def __init__(self, *, rich_log_config: RichLogConfig, target: ConsoleTarget) -> None:
        super().__init__()
        self._rich_log_config = rich_log_config
        self._target = target
        self._rich_handler: RichHandler | None = None

    @override
    def make_handler(self) -> logging.Handler:
        require_rich(message=CONSOLE_SINK_MISSING_MESSAGE)
        from rich.console import Console
        from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
        from rich.logging import RichHandler
        from rich.text import Text

        # Declared here because ``RichHandler`` is imported here, which is what keeps Rich off the import
        # path of a process that selected another sink. ``RichHandler`` overrides ``emit`` and does not
        # restore the ``try``/``handleError`` the stdlib's own handlers put around theirs, so anything
        # raised while rendering leaves the log call: a message carrying a tag-shaped span — `list[int]` in
        # a type complaint, or a bracketed path, both of which an error message is made of — raises
        # ``MarkupError`` out of `log.error` and replaces whatever was being reported with itself. A log
        # call never raises, so the guard goes back on and a line Rich cannot render gets the stdlib's own
        # recovery instead.
        class GuardedRichHandler(RichHandler):
            @override
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    super().emit(record)
                except Exception:  # ruff: ignore[blind-except]
                    self.handleError(record)

            @override
            def render_message(self, record: logging.LogRecord, message: str) -> ConsoleRenderable:
                """The message, or the layout the call named, then the fields as a styled ``key=value`` suffix, then any traceback text.

                The suffix is assembled as ``Text`` from styled segments and appended after the highlighter has
                run on the message, so neither the markup setting nor the highlighter ever reads a field's value.
                A layout that cannot be filled, whatever it raises, falls back to the message, and every field
                then goes to the suffix. The dispatch stamps a layout only on a call whose content is a string,
                so a structured content, which only its message renders, never meets one.

                With Rich tracebacks off, what Rich hands over is the formatter's whole output: the message line,
                then the exception's text and any stack text. That tail is split off the line and printed under
                it, after the suffix, so the fields stay on the line they describe and a layout keeps the
                traceback. It is printed as plain text, so nothing in a traceback is ever read as markup. A record
                with no such text renders exactly as before.
                """
                formatter = self.formatter
                formatted_line = formatter.formatMessage(record) if formatter is not None else message
                message_line = formatted_line if message.startswith(formatted_line) else message
                appended_text = message[len(message_line) :]
                fields = attached_fields(record=record)
                presented_fields: frozenset[str] = frozenset()
                message_text: ConsoleRenderable | None = None
                layout_name = record.__dict__.get(LAYOUT_MARK)
                layout = console_layout(name=layout_name) if isinstance(layout_name, str) else None
                if layout is not None:
                    try:
                        layout_markup = layout.render_markup(fields=fields)
                        # No emoji codes either: a value spelled `:fire:` is a value, not a picture.
                        message_text = Text.assemble(channel_prefix(logger_name=record.name), Text.from_markup(layout_markup, emoji=False))
                        presented_fields = layout.presented_fields
                    except Exception:  # ruff: ignore[blind-except]
                        # A layout's derivation is code each layout brings, filled with values each call
                        # chooses, so what it can raise is open-ended: a missing field, a refused value, a
                        # template Rich refuses, or arithmetic on a value nobody bounded. A layout costs
                        # nothing but itself, so whatever it raised, the line falls back to its message.
                        message_text = None
                if message_text is None:
                    message_text = super().render_message(record, message_line)
                if isinstance(message_text, Text):
                    segments = field_suffix_segments(fields=fields, presented_fields=presented_fields)
                    if segments:
                        message_text.append_text(Text.assemble(*segments))
                    if appended_text:
                        # The formatter puts a line break before the exception text only when the message does
                        # not already end in one, and the suffix or a layout now stands between the two.
                        if not message_text.plain.endswith("\n") and not appended_text.startswith("\n"):
                            message_text.append("\n")
                        message_text.append_text(Text(appended_text))
                return message_text

        config = self._rich_log_config
        highlighter: Highlighter
        match config.highlighter_name:
            case HighlighterName.JSON:
                highlighter = JSONHighlighter()
            case HighlighterName.REPR:
                highlighter = ReprHighlighter()
        handler = GuardedRichHandler(
            console=Console(file=stream_for_target(target=self._target)),
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
        self._rich_handler = handler
        return handler

    @override
    def redirect_to_stderr(self) -> None:
        # The handler is built first, so a process without Rich meets the same named failure as at boot. The
        # guard is spelled out beside the import as well: a handler this sink already holds proves Rich is
        # there, but that is a fact about the object rather than about this function, and the import guard
        # reads functions.
        require_rich(message=CONSOLE_SINK_MISSING_MESSAGE)
        if self._rich_handler is None:
            _ = self.handler
        if self._rich_handler is not None:
            from rich.console import Console

            self._rich_handler.console = Console(file=sys.stderr)
