"""The ``console`` sink: the Rich handler with the emoji formatter and every ``[runtime.log.rich_log]`` setting.

Rich is the ``cli`` extra. It is imported when the handler is built and nowhere else in this module, so a
process that selects another sink never loads it, and one that selects this sink without Rich installed
fails at boot with the extra to install and the ``json`` alternative named, per the plugin system's
fail-at-use rule.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from typing_extensions import override

from pipelex.tools.log.log_config import HighlighterName
from pipelex.tools.log.log_formatter import EmojiLogFormatter
from pipelex.tools.log.log_sink import LogSink, LogSinkMethod, stream_for_target
from pipelex.tools.misc.rich_extra import require_rich

if TYPE_CHECKING:
    import logging

    from rich.logging import RichHandler

    from pipelex.system.console_target import ConsoleTarget
    from pipelex.tools.log.log_config import RichLogConfig


class ConsoleLogSink(LogSink):
    """Today's console rendering, byte for byte: a ``RichHandler`` on the configured stream."""

    def __init__(self, *, rich_log_config: RichLogConfig, target: ConsoleTarget) -> None:
        super().__init__()
        self._rich_log_config = rich_log_config
        self._target = target
        self._rich_handler: RichHandler | None = None

    @override
    def make_handler(self) -> logging.Handler:
        require_rich(
            message=(
                f"The '{LogSinkMethod.CONSOLE}' log sink renders through Rich. Install the extra, "
                f"or select the '{LogSinkMethod.JSON}' sink in [runtime.log] for a process with no terminal."
            )
        )
        from rich.console import Console
        from rich.highlighter import Highlighter, JSONHighlighter, ReprHighlighter
        from rich.logging import RichHandler

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
        # The handler is built first, so a process without Rich meets the same named failure as at boot,
        # and Rich is imported only once the handler that proves it is installed exists.
        if self._rich_handler is None:
            _ = self.handler
        if self._rich_handler is not None:
            from rich.console import Console

            self._rich_handler.console = Console(file=sys.stderr)
