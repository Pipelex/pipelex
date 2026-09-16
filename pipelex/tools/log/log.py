from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

from pipelex.tools.log.log_context import bind_log_context
from pipelex.tools.log.log_dispatch import LogDispatch
from pipelex.tools.log.log_holding import ForwardedRecordFilter, HoldingLogHandler
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_OFF, LOGGING_LEVEL_VERBOSE, LogLevel

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from contextlib import AbstractContextManager

    from pipelex.tools.log.log_config import LogConfig
    from pipelex.tools.log.log_context import LogContext
    from pipelex.tools.log.log_sink import LogSink


def _finish_teardown_step(*, sink: LogSink, verb: str, step: Callable[[], None]) -> None:
    """Run one step of a sink's teardown and let nothing it raises escape.

    A closed stream, a test capture or a redirected process stream torn down first, stays silent: the
    stdlib's own shutdown tolerates the same two. Anything else, an exporter that cannot reach its
    collector or a processor whose shutdown raises, is a fact about the sink, said on stderr with the
    step that failed, and never a reason to leave the teardown half done.
    """
    try:
        step()
    except (OSError, ValueError):
        pass
    except Exception as exc:  # ruff: ignore[blind-except]
        sys.stderr.write(f"The log sink {type(sink).__name__} failed to {verb} at reset: {exc!r}\n")


class Log:
    """A class for managing logging configurations and operations.

    Configuration is two steps, because the sink is a plugin capability and plugin discovery runs a
    little after the configuration is read: ``configure`` sets the levels and holds every record on the
    root logger, then ``install_sink`` puts the selected sink's handler in its place and replays what was
    held through it. ``reset`` removes exactly what those two installed and leaves every other handler,
    a host's or a test's, where it was.
    """

    ########################################################
    # Init and Configure
    ########################################################

    def __init__(self):
        """Initialize the Log class with default attributes."""
        self._log_config_instance: LogConfig | None = None
        self._holding_handler: HoldingLogHandler | None = None
        self._sink: LogSink | None = None
        self.log_dispatch: LogDispatch = LogDispatch()

    @property
    def sink(self) -> LogSink | None:
        """The installed sink, or ``None`` before ``install_sink`` and after ``reset``."""
        return self._sink

    @property
    def is_configured(self) -> bool:
        """Whether ``configure`` has run and ``reset`` has not, which is what makes a later ``configure`` refuse."""
        return self._log_config_instance is not None

    def reset(self):
        """Remove what ``configure`` and ``install_sink`` put on the root logger, and forget the configuration.

        The sink's handler is flushed and closed, which is where a batching sink ships what it still
        holds, and nothing that flush or close raises escapes: this runs first in the runtime's release
        of its process globals, and an error out of it would skip the rest and leave the process
        unbootable. The close runs whatever the flush did, since the close is what stops an exporter's
        thread, ships its last batch and unregisters what it put at exit. A holding handler still in
        place, because the boot died before its sink arrived, is closed too, and what it holds gets the
        stdlib's last-resort handling.
        """
        root_logger = logging.getLogger()
        if self._sink is not None:
            sink, self._sink = self._sink, None
            handler = sink.handler
            root_logger.removeHandler(handler)
            try:
                _finish_teardown_step(sink=sink, verb="flush", step=handler.flush)
            finally:
                _finish_teardown_step(sink=sink, verb="close", step=handler.close)
        if self._holding_handler is not None:
            root_logger.removeHandler(self._holding_handler)
            self._holding_handler.close()
            self._holding_handler = None
        self._log_config_instance = None
        self.log_dispatch.reset()

    def configure_if_unset(self, log_config: LogConfig) -> bool:
        """Configure logging unless already configured.

        Useful for entry points that may be reached after another caller (a library
        embedding Pipelex, an interleaved test) has already initialized logging.
        ``configure`` itself is once-per-process and raises on a second call; this
        guarded variant returns False instead.

        Args:
            log_config: The log configuration to use.

        Returns:
            True if configuration was applied, False if logging was already configured.
        """
        if self._log_config_instance is not None:
            return False
        self.configure(log_config=log_config)
        return True

    def configure(self, log_config: LogConfig):
        """Configure the logging system with the given project name and log configuration.

        Args:
            log_config (LogConfig): The log configuration to use.

        Raises:
            RuntimeError: If the log configuration is already set.

        """
        if self._log_config_instance is not None:
            msg = "LogConfig is already set. You can only call log.configure() once."
            raise RuntimeError(msg)

        self.log_dispatch.configure(log_config=log_config)

        self._log_config_instance = log_config

        # Configure the root logger: the levels now, the sink when discovery hands it over. Until then
        # every record is held, so nothing a boot says is lost or written in a shape nothing chose.
        root_logger = logging.getLogger()
        root_logger.setLevel(log_config.default_log_level.int_logging_level)
        self._holding_handler = HoldingLogHandler()
        root_logger.addHandler(self._holding_handler)

        self.set_levels_for_packages(package_log_levels=log_config.package_log_levels)

        self.verbose("Logs configured and config set")

    def install_sink(self, sink: LogSink):
        """Put the sink's handler on the root logger and replay through it every record held since ``configure``.

        The handler is built here, so a sink whose dependency is missing fails at this call, at boot,
        with the extra named. Once per configuration: a second sink is refused, as a second ``configure`` is.

        Raises:
            RuntimeError: If logging is not configured, or a sink is already installed.
            MissingDependencyError: If the sink's handler needs a package that is not installed.

        """
        if self._log_config_instance is None:
            msg = "Logging is not configured. Call log.configure() before log.install_sink()."
            raise RuntimeError(msg)
        if self._sink is not None:
            msg = "A log sink is already installed. You can only call log.install_sink() once per configuration."
            raise RuntimeError(msg)

        handler = sink.handler
        # Ahead of every other filter, so the sink's processors never run on a record it rejects.
        handler.filters.insert(0, ForwardedRecordFilter())
        root_logger = logging.getLogger()
        # Recorded before the replay: a handler that raises on one held record leaves the sink
        # installed all the same, so ``reset`` finds it and removes it rather than leaking it into
        # the next boot.
        self._sink = sink
        if self._holding_handler is None:
            root_logger.addHandler(handler)
            return
        # The held records drain first, so every one of them precedes whatever is emitted from now
        # on. A record emitted meanwhile reaches the holding handler, which forwards it once and
        # marks it; once the sink's handler is on the root logger too, the guard on it rejects the
        # root's own delivery of that same record, so nothing is delivered twice, and nothing reaches
        # neither, since one of the two handlers is on the root at every instant.
        holding, self._holding_handler = self._holding_handler, None
        try:
            holding.release_to(handler=handler)
        finally:
            root_logger.addHandler(handler)
            root_logger.removeHandler(holding)
            holding.close()

    def _should_ignore(self, problem_id: str | None = None) -> bool:
        """Check if a log message should be ignored based on the problem ID.

        Args:
            problem_id (str | None): The problem ID to check.

        Returns:
            bool: True if the message should be ignored, False otherwise.

        """
        if self._log_config_instance is None:
            return False
        return bool(problem_id) and problem_id in self._log_config_instance.silenced_problem_ids

    ########################################################
    # Public methods
    ########################################################

    def redirect_to_stderr(self):
        """Point the installed sink at stderr when it writes to a process stream.

        Used by the agent CLI to ensure no log output pollutes stdout. A no-op before a sink is
        installed, and for a sink that writes to no process stream.
        """
        if self._sink is not None:
            self._sink.redirect_to_stderr()

    def set_level_by_int(self, *, level_int: int):
        """Set the log level using an integer value.

        Args:
            level_int (int): The integer representation of the log level.

        """
        logging.getLogger().setLevel(level_int)

    def set_level_by_name(self, level_name: str):
        """Set the log level using a string name.

        Args:
            level_name (str): The name of the log level.

        """
        if level_name.upper() == LogLevel.DEV:
            level = LOGGING_LEVEL_DEV
        elif level_name.upper() == LogLevel.OFF:
            level = LOGGING_LEVEL_OFF
        else:
            level = getattr(logging, level_name.upper())
        self.set_level_by_int(level_int=level)

    def set_level(self, level: LogLevel):
        """Set the default log level for all loggers.

        Args:
            level (LogLevel): The log level to set.

        """
        self.set_level_by_int(level_int=level.int_logging_level)

    def set_level_for_package(self, package_name: str, *, level: LogLevel):
        """Set the log level for a specific package.

        Args:
            package_name (str): The name of the package.
            level (LogLevel): The log level to set for the package.

        """
        logger_name = package_name.replace("-", ".")
        logging.getLogger(logger_name).setLevel(level.int_logging_level)

    def set_levels_for_packages(self, package_log_levels: dict[str, LogLevel]):
        """Set log levels for multiple packages.

        Args:
            package_log_levels (Dict[str, LogLevel]): A dictionary mapping package names to log levels.

        """
        for package_name, level in package_log_levels.items():
            self.set_level_for_package(package_name=package_name, level=level)

    def context(
        self,
        *,
        request_id: str | None = None,
        pipeline_run_id: str | None = None,
        pipe_run_id: str | None = None,
    ) -> AbstractContextManager[LogContext]:
        """Bind the run-scoped identifiers onto every record emitted inside the block.

        Bound at a process entry from the payload it received — ``PipeRun.run`` binds from the job's
        metadata — and released when the block exits. Nested blocks merge, the inner overriding the
        outer for the identifiers it gives; a ``None`` inherits rather than clears.
        """
        return bind_log_context(request_id=request_id, pipeline_run_id=pipeline_run_id, pipe_run_id=pipe_run_id)

    def verbose(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log a verbose message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.

        """
        severity = LOGGING_LEVEL_VERBOSE
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline, fields=fields)

    def debug(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log a debug message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.

        """
        severity = logging.DEBUG
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline, fields=fields)

    def dev(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log a development message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.

        """
        severity = LOGGING_LEVEL_DEV
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline, fields=fields)

    def info(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log an info message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.

        """
        severity = logging.INFO
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline, fields=fields)

    def warning(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        problem_id: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log a warning message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.
            problem_id (str | None, optional): A problem ID to associate with the warning. Defaults to None.

        """
        if self._should_ignore(problem_id=problem_id):
            return
        severity = logging.WARNING
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline, fields=fields)

    def error(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        include_exception: bool = False,
        problem_id: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log an error message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.
            include_exception (bool, optional): Whether to include exception information. Defaults to False.
            problem_id (str | None, optional): A problem ID to associate with the error. Defaults to None.

        """
        if self._should_ignore(problem_id=problem_id):
            return
        severity = logging.ERROR
        self.log_dispatch.dispatch(
            content=content,
            severity=severity,
            title=title,
            inline=inline,
            include_exception=include_exception,
            fields=fields,
        )

    def critical(
        self,
        content: str | Any,
        *,
        title: str | None = None,
        inline: str | None = None,
        include_exception: bool = False,
        problem_id: str | None = None,
        fields: Mapping[str, Any] | None = None,
    ):
        """Log a critical message.

        Args:
            content (Union[str, Any]): The content to log.
            title (str | None, optional): The title of the log message. Defaults to None.
            inline (str | None, optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            fields (Mapping[str, Any] | None, optional): Named values carried as attributes of the record, never rendered into the message.
            include_exception (bool, optional): Whether to include exception information. Defaults to False.
            problem_id (str | None, optional): A problem ID to associate with the critical message. Defaults to None.

        """
        if self._should_ignore(problem_id=problem_id):
            return
        severity = logging.CRITICAL
        self.log_dispatch.dispatch(
            content=content,
            severity=severity,
            title=title,
            inline=inline,
            include_exception=include_exception,
            fields=fields,
        )


log = Log()
