"""Where a ``log.<level>(...)`` call becomes a stdlib ``LogRecord``.

One frame lookup at a fixed depth names the emitting module and locates the call; the logger is named
after that module; the bound context, the call's fields and any structured content ride the record as
attributes through ``extra``; and the console keeps the narrative line it always had. Nothing here
walks the stack, and nothing here raises for want of a configuration: before ``configure`` the record
goes to the stdlib's default handling.
"""

from __future__ import annotations

import inspect
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from pipelex.tools.log.log_config import CallerInfoTemplate, LogConfig
from pipelex.tools.log.log_context import get_log_context
from pipelex.tools.log.log_fields import attach_log_record_extra, build_log_record_extra
from pipelex.tools.log.log_redaction import redact_secret_entries
from pipelex.tools.misc.json_utils import purify_json, purify_json_dict, purify_json_list

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import FrameType

    # The triple ``sys.exc_info`` returns while an exception is being handled.
    ExcInfo = tuple[type[BaseException], BaseException, Any]

# The frames between ``_caller_frame`` and the code that called ``log.<level>(...)``: the helper's own
# frame, then ``LogDispatch.dispatch``, then the ``Log`` method. A change to that call chain moves this number.
CALLER_FRAME_DEPTH = 3
UNKNOWN_MODULE_NAME = "unknown"
UNKNOWN_FILE_NAME = "(unknown file)"
UNKNOWN_FUNCTION_NAME = "(unknown function)"


def _caller_frame() -> FrameType | None:
    """The frame of the code that called ``log.<level>(...)``, or ``None`` when the stack is shallower than that.

    A fixed number of ``f_back`` hops from this frame: no stack is materialised and no module is looked up.
    """
    frame = inspect.currentframe()
    for _ in range(CALLER_FRAME_DEPTH):
        if frame is None:
            return None
        frame = frame.f_back
    return frame


def _module_name(*, frame: FrameType | None) -> str:
    if frame is None:
        return UNKNOWN_MODULE_NAME
    module_name = cast("str | None", frame.f_globals.get("__name__"))
    return module_name or UNKNOWN_MODULE_NAME


def _active_exc_info() -> ExcInfo | None:
    """The exception being handled, as the record's ``exc_info``, or ``None`` outside any ``except`` block."""
    exc_type, exc_value, exc_traceback = sys.exc_info()
    if exc_type is None or exc_value is None:
        return None
    return exc_type, exc_value, exc_traceback


class LogDispatch:
    """Turns the facade's calls into records on module-named stdlib loggers."""

    ########################################################
    # Init and Configure
    ########################################################
    # TODO: more elegant init for log_dispatch / log
    def __init__(self):
        self._log_config_instance: LogConfig | None = None

    def reset(self):
        """Reset the log dispatch."""
        self._log_config_instance = None

    def configure(self, log_config: LogConfig):
        """Configures the LogDispatch with log configuration.

        Args:
            log_config (LogConfig): The log configuration to use.

        Raises:
            RuntimeError: If LogConfig is already set.

        """
        if self._log_config_instance is not None:
            msg = "LogConfig is already set. You can only call log.configure() once."
            raise RuntimeError(msg)
        self._log_config_instance = log_config

    ########################################################
    # Dispatch
    ########################################################

    def dispatch(
        self,
        content: str | Any,
        *,
        severity: int,
        title: str | None = None,
        inline: str | None = None,
        include_exception: bool = False,
        fields: Mapping[str, Any] | None = None,
    ):
        """Emit one record for the call, on the logger named after the calling module.

        Args:
            content: The content to log. A string is the message; anything else is rendered as JSON for
                the console and carried as the ``data`` attribute for structured sinks.
            severity: The severity level of the log message.
            title: A title rendered above the content. Defaults to None.
            inline: A title rendered inline before a string content, used only when ``title`` is None.
            include_exception: Whether to carry the exception being handled on the record, as its
                ``exc_info``, for every sink to render its own way. Nothing is spliced into the message.
            fields: Named values carried as attributes of the record, never rendered into the message.

        """
        caller_frame = _caller_frame()
        module_name = _module_name(frame=caller_frame)
        log_config = self._log_config_instance
        logger = logging.getLogger(module_name)
        if not logger.isEnabledFor(severity):
            return

        message, data = self._render_content(content=content, title=title, inline=inline, log_config=log_config)
        if log_config is not None and log_config.is_caller_info_enabled and caller_frame is not None:
            caller_info_str = self._caller_info(frame=caller_frame, module_name=module_name, log_config=log_config)
            message = f"{caller_info_str}: {message}"
        exc_info = _active_exc_info() if include_exception else None

        extra = build_log_record_extra(context=get_log_context(), fields=fields, data=data)
        self._emit_record(message=message, severity=severity, logger=logger, caller_frame=caller_frame, exc_info=exc_info, extra=extra)

    ########################################################
    # Private methods
    ########################################################

    def _render_content(
        self,
        *,
        content: str | Any,
        title: str | None,
        inline: str | None,
        log_config: LogConfig | None,
    ) -> tuple[str, Any | None]:
        """The console line for the content and, for structured content, its JSON-ready form."""
        if isinstance(content, str):
            if title is not None:
                return f"{title}:\n{content}", None
            if inline is not None:
                return f"{inline}: {content}", None
            return content, None

        if content is None:
            if title is not None:
                return f"{title}:\nNone", None
            return "None", None

        indent = log_config.json_logs_indent if log_config is not None else None
        data: Any | None
        try:
            if isinstance(content, dict):
                _, rendered = purify_json_dict(data=content, indent=indent, is_warning_enabled=True)
            elif isinstance(content, list):
                _, rendered = purify_json_list(data=cast("list[Any]", content), indent=indent, is_truncate_bytes_enabled=True)
            else:
                _, rendered = purify_json(data=content, indent=indent, is_truncate_bytes_enabled=True, is_warning_enabled=False)
            # The structure the helpers hand back is the caller's own object whenever it was JSON-clean as
            # given, and a sink that serializes later would read whatever the caller did to it since. The
            # data is therefore the rendering re-read: a snapshot of the call, JSON-ready whatever it held.
            data = json.loads(rendered)
            if log_config is not None and log_config.redaction.is_enabled:
                # Redacted by name before the message is settled, because the message is this rendering and
                # the redaction processor reads it as text: an entry named like a secret whose value is an
                # object or a number would keep its value there while ``data`` lost it. Rendered again only
                # when an entry was replaced, so every other line keeps the helpers' own rendering.
                redacted = redact_secret_entries(value=data)
                if redacted != data:
                    data = redacted
                    rendered = json.dumps(redacted, indent=indent)
        except (TypeError, ValueError):
            # What ``json`` refuses outright, a circular reference or a mapping with a non-string key,
            # is rendered as its ``repr`` and carries no ``data``: a log call never raises. The names
            # are redacted on this path too, and not only where the serialization worked: the ``repr``
            # of an entry holding an object is beyond what the string families can read back out of
            # text, so a fallback that skipped it would be the one rendering in which a secret the
            # redaction is configured to remove reaches the sink whole.
            is_redacting = log_config is not None and log_config.redaction.is_enabled
            fallback = cast("object", redact_secret_entries(value=content) if is_redacting else content)
            rendered = repr(fallback)
            data = None
        message = f"\n{rendered}"
        if title is not None:
            message = f"{title}:{message}"
        return message, data

    def _caller_info(self, *, frame: FrameType, module_name: str, log_config: LogConfig) -> str:
        """The caller's location in the configured template, read off the frame without touching the source file."""
        caller_path = Path(frame.f_code.co_filename)
        try:
            caller_path = caller_path.relative_to(Path.cwd())
        except ValueError:
            # This can happen if the file is on a different drive (on Windows)
            # In this case, we'll keep the absolute path
            pass
        template_str = CallerInfoTemplate.for_template_key(key=log_config.caller_info_template)
        return template_str.format(file=str(caller_path), line=frame.f_lineno, func=frame.f_code.co_name, module=module_name)

    def _emit_record(
        self,
        *,
        message: str,
        severity: int,
        logger: logging.Logger,
        caller_frame: FrameType | None,
        exc_info: ExcInfo | None,
        extra: dict[str, Any],
    ):
        """Build the record at the caller's location, attach what it carries, and hand it to the logger's handlers.

        The record is built first and the extra attached afterwards: ``makeRecord`` raises on a key the
        record already owns, and what it owns is only known once the installed record factory has run.
        """
        if caller_frame is None:
            pathname, lineno, func_name = UNKNOWN_FILE_NAME, 0, UNKNOWN_FUNCTION_NAME
        else:
            pathname, lineno, func_name = caller_frame.f_code.co_filename, caller_frame.f_lineno or 0, caller_frame.f_code.co_name
        record = logger.makeRecord(
            name=logger.name,
            level=severity,
            fn=pathname,
            lno=lineno,
            msg=message,
            args=(),
            exc_info=exc_info,
            func=func_name,
        )
        attach_log_record_extra(record=record, extra=extra)
        logger.handle(record)
