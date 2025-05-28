import logging
from typing import Any, Dict, Optional, Union

from pipelex.tools.log.log_config import (
    LogConfig,
    LogLevel,
)
from pipelex.tools.log.log_dispatch import LogDispatch
from pipelex.tools.log.log_formatter import EmojiLogFormatter, LevelAndEmojiLogFormatter
from pipelex.tools.log.log_levels import LOGGING_LEVEL_DEV, LOGGING_LEVEL_OFF, LOGGING_LEVEL_VERBOSE


class Log:
    """
    A class for managing logging configurations and operations.
    """

    ########################################################
    # Init and Configure
    ########################################################

    def __init__(self):
        """
        Initialize the Log class with default attributes.
        """
        self.project_name: Optional[str] = None
        self._log_config_instance: Optional[LogConfig] = None
        self.rich_handler: Optional[logging.Handler] = None
        self.poor_handler: Optional[logging.Handler] = None
        self.log_dispatch: LogDispatch = LogDispatch()

    @property
    def _log_config(self) -> LogConfig:
        """
        Get the log configuration, raising an error if it's not set.

        Returns:
            LogConfig: The current log configuration.

        Raises:
            RuntimeError: If the log configuration is not set.
        """
        if self._log_config_instance is None:
            raise RuntimeError("LogConfig is not set. You must initialize Pipelex first.")
        return self._log_config_instance

    def reset(self):
        """
        Reset the logging system.
        """
        # Remove all handlers from the root logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

        # Remove handlers from poor loggers
        if self._log_config_instance:
            poor_loggers = set(self._log_config_instance.poor_loggers + [self._log_config_instance.generic_poor_logger])
            for logger_name in poor_loggers:
                logger = logging.getLogger(logger_name)
                for handler in logger.handlers[:]:
                    logger.removeHandler(handler)
                    handler.close()

        logging.shutdown()
        self.project_name = None
        self._log_config_instance = None
        self.rich_handler = None
        self.poor_handler = None
        self.log_dispatch.reset()

    def configure(
        self,
        project_name: str,
        log_config: LogConfig,
    ):
        """
        Configure the logging system with the given project name and log configuration.

        Args:
            project_name (str): The name of the project.
            log_config (LogConfig): The log configuration to use.

        Raises:
            RuntimeError: If the log configuration is already set.
        """
        if self._log_config_instance is not None:
            raise RuntimeError("LogConfig is already set. You can only call log.configure() once.")

        self.log_dispatch.configure(
            project_name=project_name,
            log_config=log_config,
        )

        self._log_config_instance = log_config

        self.project_name = project_name
        self.rich_handler = log_config.rich_log_config.make_rich_handler()
        self.rich_handler.setFormatter(EmojiLogFormatter())

        # Configure the root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_config.default_log_level.int_logging_level)
        root_logger.addHandler(self.rich_handler)

        self.poor_handler = logging.StreamHandler()
        self.poor_handler.setFormatter(LevelAndEmojiLogFormatter())
        poor_loggers = set(log_config.poor_loggers + [log_config.generic_poor_logger])
        for logger_name in poor_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(log_config.default_log_level.int_logging_level)
            logger.addHandler(self.poor_handler)
            logger.propagate = False

        self.set_levels_for_packages(package_log_levels=log_config.package_log_levels)

        self.verbose("Logs configured")
        self.verbose(f"Config set for {project_name}")

    def set_poor_log_formatter(self, formatter: logging.Formatter):
        """
        Set the formatter for the poor log handler.

        Args:
            formatter (logging.Formatter): The formatter to use for poor logging.
        """
        if self.poor_handler is None:
            raise RuntimeError("Poor log handler is not set.")
        self.poor_handler.setFormatter(formatter)

    def _should_ignore(self, problem_id: Optional[str] = None) -> bool:
        """
        Check if a log message should be ignored based on the problem ID.

        Args:
            problem_id (Optional[str]): The problem ID to check.

        Returns:
            bool: True if the message should be ignored, False otherwise.
        """
        if problem_id and problem_id in self._log_config.silenced_problem_ids:
            return True
        else:
            return False

    ########################################################
    # Public methods
    ########################################################

    def set_level_by_int(self, level_int: int):
        """
        Set the log level using an integer value.

        Args:
            level_int (int): The integer representation of the log level.
        """
        logging.getLogger().setLevel(level_int)

    def set_level_by_name(self, level_name: str):
        """
        Set the log level using a string name.

        Args:
            level_name (str): The name of the log level.
        """
        if level_name.upper() == LogLevel.DEV:
            level = LOGGING_LEVEL_DEV
        elif level_name.upper() == LogLevel.OFF:
            level = LOGGING_LEVEL_OFF
        else:
            level = getattr(logging, level_name.upper())
        self.set_level_by_int(level)

    def set_level(self, level: LogLevel):
        """
        Set the default log level for all loggers.
        Args:
            level (LogLevel): The log level to set.
        """
        # print(f"Setting default logs to {level=}")
        self.set_level_by_int(level_int=level.int_logging_level)

    def set_level_for_package(self, package_name: str, level: LogLevel):
        """
        Set the log level for a specific package.

        Args:
            package_name (str): The name of the package.
            level (LogLevel): The log level to set for the package.
        """
        logger_name = package_name.replace("-", ".")
        logging.getLogger(logger_name).setLevel(level.int_logging_level)

    def set_levels_for_packages(self, package_log_levels: Dict[str, LogLevel]):
        """
        Set log levels for multiple packages.

        Args:
            package_log_levels (Dict[str, LogLevel]): A dictionary mapping package names to log levels.
        """
        for package_name, level in package_log_levels.items():
            self.set_level_for_package(package_name=package_name, level=level)

    def verbose(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
    ):
        """
        Log a verbose message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
        """
        severity = LOGGING_LEVEL_VERBOSE
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline)

    def debug(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
    ):
        """
        Log a debug message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
        """
        severity = logging.DEBUG
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline)

    def dev(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
    ):
        """
        Log a development message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
        """
        severity = LOGGING_LEVEL_DEV
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline)

    def info(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
    ):
        """
        Log an info message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
        """
        severity = logging.INFO
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline)

    def warning(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
        problem_id: Optional[str] = None,
    ):
        """
        Log a warning message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            problem_id (Optional[str], optional): A problem ID to associate with the warning. Defaults to None.
        """
        if self._should_ignore(problem_id=problem_id):
            return
        severity = logging.WARNING
        self.log_dispatch.dispatch(content=content, severity=severity, title=title, inline=inline)

    def error(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
        problem_id: Optional[str] = None,
    ):
        """
        Log an error message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            include_exception (bool, optional): Whether to include exception information. Defaults to False.
            problem_id (Optional[str], optional): A problem ID to associate with the error. Defaults to None.
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
        )

    def critical(
        self,
        content: Union[str, Any],
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
        problem_id: Optional[str] = None,
    ):
        """
        Log a critical message.

        Args:
            content (Union[str, Any]): The content to log.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            include_exception (bool, optional): Whether to include exception information. Defaults to False.
            problem_id (Optional[str], optional): A problem ID to associate with the critical message. Defaults to None.
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
        )


log = Log()
