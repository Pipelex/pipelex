from __future__ import annotations

import inspect
import logging
import os
import traceback
from typing import Any, Optional, Union, cast, overload

from pipelex.tools.log.log_config import CallerInfoTemplate, LogConfig, LogMode
from pipelex.tools.misc.json_utils import purify_json, purify_json_dict, purify_json_list


class LogDispatch:
    """
    A class for handling log dispatching to the console (and optionally other sinks).
    """

    ########################################################
    # Init and Configure
    ########################################################
    # TODO: more elegant init for log_dispatch / log
    def __init__(self) -> None:
        self.project_name: Optional[str] = None
        self._log_config_instance: Optional[LogConfig] = None
        self.log_mode: LogMode = LogMode.RICH

    def set_log_mode(self, mode: LogMode) -> None:
        self.log_mode = mode

    def reset(self) -> None:
        """
        Reset the log dispatch.
        """
        self.project_name = None
        self._log_config_instance = None

    @property
    def _log_config(self) -> LogConfig:
        """
        Retrieves the log configuration.

        Raises:
            RuntimeError: If LogConfig is not set.

        Returns:
            LogConfig: The current log configuration.
        """
        if self._log_config_instance is None:
            raise RuntimeError("LogConfig is not set. You must call pipelex_hub.set_config().")
        return self._log_config_instance

    def configure(
        self,
        project_name: str,
        log_config: LogConfig,
    ) -> None:
        """
        Configures the LogDispatch with project name and log configuration.

        Args:
            project_name: The name of the project.
            log_config: The log configuration to use.

        Raises:
            RuntimeError: If LogConfig is already set.
        """
        if self._log_config_instance is not None:
            raise RuntimeError("LogConfig is already set. You can only call log.configure() once.")
        self._log_config_instance = log_config
        self.project_name = project_name
        self.log_mode = log_config.log_mode

    ########################################################
    # Public API
    ########################################################

    def dispatch(
        self,
        content: Union[str, Any],
        severity: int,
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
    ) -> None:
        """
        Dispatches a log message to appropriate logging methods based on content type.

        Args:
            content: The content to be logged.
            severity: The severity level of the log message.
            title: A block title for the log message (prefix + newline before body).
            inline: Inline title (used only if `title` is None).
            include_exception: Whether to include exception traceback.
        """
        caller_info_str: Optional[str] = None

        if self._log_config.is_caller_info_enabled:
            frame0 = inspect.currentframe()
            frame1 = frame0.f_back if frame0 is not None else None
            caller_frame = frame1.f_back if frame1 is not None else None
            if caller_frame is not None:
                caller_info = inspect.getframeinfo(caller_frame)
                caller_file = caller_info.filename
                cwd = os.getcwd()
                try:
                    caller_file = os.path.relpath(caller_file, cwd)
                except ValueError:
                    # Different drive (Windows) etc. → keep absolute path
                    pass
                caller_line = caller_info.lineno
                caller_func = caller_info.function
                template_str = CallerInfoTemplate.for_template_key(key=self._log_config.caller_info_template)
                caller_info_str = template_str.format(file=caller_file, line=caller_line, func=caller_func)

        if isinstance(content, str):
            self._log_message(
                message=content,
                severity=severity,
                caller_info_str=caller_info_str,
                title=title,
                inline=inline,
                include_exception=include_exception,
            )
        else:
            self._log_data(
                data=content,
                severity=severity,
                caller_info_str=caller_info_str,
                title=title,
                include_exception=include_exception,
            )

    ########################################################
    # Private methods
    ########################################################

    def _log_message(
        self,
        message: str,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
    ) -> None:
        """
        Logs a plain message.
        """
        if title is not None:
            message = f"{title}:\n{message}"
        elif inline is not None:
            message = f"{inline}: {message}"

        message_for_console = f"{caller_info_str}: {message}" if caller_info_str is not None else message

        if include_exception:
            message_for_console = f"{message_for_console}\n{traceback.format_exc()}"

        self._log_to_console(message=message_for_console, severity=severity)

    # -------- typed overloads so Pyright can narrow cleanly ----------
    @overload
    def _log_data(
        self,
        data: None,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = ...,
        include_exception: bool = ...,
    ) -> None: ...
    @overload
    def _log_data(
        self,
        data: dict[str, Any],
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = ...,
        include_exception: bool = ...,
    ) -> None: ...
    @overload
    def _log_data(
        self,
        data: list[Any],
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = ...,
        include_exception: bool = ...,
    ) -> None: ...
    @overload
    def _log_data(
        self,
        data: object,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = ...,
        include_exception: bool = ...,
    ) -> None: ...

    def _log_data(
        self,
        data: object,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = None,
        include_exception: bool = False,
    ) -> None:
        """
        Logs potentially structured data (dict/list/other), with strict typing.
        """
        # Build prefix once
        prefix_parts: list[str] = []
        if caller_info_str is not None:
            prefix_parts.append(f"{caller_info_str}:")
        if title is not None:
            prefix_parts.append(f"{title}:")
        prefix = " ".join(prefix_parts)

        if data is None:
            body = "None"

        elif isinstance(data, dict):
            dict_data = cast(dict[str, Any], data)
            _, body = purify_json_dict(
                data=dict_data,
                indent=self._log_config.json_logs_indent,
                is_warning_enabled=True,
            )

        elif isinstance(data, list):
            list_data = cast(list[Any], data)
            _, body = purify_json_list(
                data=list_data,
                indent=self._log_config.json_logs_indent,
                is_truncate_bytes_enabled=True,
            )

        else:
            _, body = purify_json(
                data=data,
                indent=self._log_config.json_logs_indent,
                is_truncate_bytes_enabled=True,
                is_warning_enabled=False,
            )

        message = f"{prefix}\n{body}" if prefix else f"\n{body}"
        if include_exception:
            message += f"\n{traceback.format_exc()}"
        self._log_to_console(message=message, severity=severity)

    def _log_to_console(self, message: str, severity: int) -> None:
        """
        Logs a message to the console.
        """
        if not self._log_config.is_console_logging_enabled:
            return

        match self.log_mode:
            case LogMode.RICH:
                # Rich mode: currently a no-op here; upstream formatter may handle it.
                pass
            case LogMode.POOR:
                logger = logging.getLogger(self._log_config.generic_poor_logger)
                logger.log(level=severity, msg=message, stacklevel=6)

        # Derive an origin logger name based on the first non-logging frame
        stack = inspect.stack()
        try:
            logging_module_path = os.path.abspath(__file__)
            log_origin_name = "unknown"

            for frame_info in stack[1:]:
                try:
                    frame = frame_info.frame
                    module = inspect.getmodule(frame)
                    if module is None:
                        continue

                    module_file = os.path.abspath(module.__file__) if hasattr(module, "__file__") and module.__file__ is not None else None
                    if module_file is None:
                        continue

                    if module_file == logging_module_path or module_file.endswith("/log.py"):
                        continue

                    if module.__name__ == "__main__":
                        if self.project_name is None:
                            raise RuntimeError("Project name is not set. You must call initialize Pipelex first.")
                        log_origin_name = self.project_name
                    else:
                        log_origin_name = module.__name__.split(sep=".", maxsplit=1)[0]
                    break
                finally:
                    del frame_info

            logger = logging.getLogger(log_origin_name)
            logger.log(level=severity, msg=message, stacklevel=5)
        finally:
            if stack:
                del stack
