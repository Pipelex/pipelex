import inspect
import logging
import os
import traceback
from typing import Any, List, Optional, Union

from kajson.sandbox_manager import sandbox_manager

from pipelex.tools.log.log_config import (
    CallerInfoTemplate,
    LogConfig,
)
from pipelex.tools.misc.json_utils import purify_json, purify_json_dict, purify_json_list


class LogDispatch:
    """
    A class for handling log dispatching to both console and Google Cloud.
    """

    ########################################################
    # Init and Configure
    ########################################################
    # TODO: more elegant init for log_dispatch / log
    def __init__(self):
        self.project_name: Optional[str] = None
        self._log_config_instance: Optional[LogConfig] = None

    def reset(self):
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
    ):
        """
        Configures the LogDispatch with project name and log configuration.

        Args:
            project_name (str): The name of the project.
            log_config (LogConfig): The log configuration to use.

        Raises:
            RuntimeError: If LogConfig is already set.
        """
        if self._log_config_instance is not None:
            raise RuntimeError("LogConfig is already set. You can only call log.configure() once.")
        self._log_config_instance = log_config
        self.project_name = project_name

    ########################################################
    # Private methods
    ########################################################

    def dispatch(
        self,
        content: Union[str, Any],
        severity: int,
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
    ):
        """
        Dispatches a log message to appropriate logging methods based on content type.

        Args:
            content (Union[str, Any]): The content to be logged.
            severity (int): The severity level of the log message.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            include_exception (bool, optional): Whether to include exception traceback. Defaults to False.
        """
        caller_info_str: Optional[str] = None
        if (
            (self._log_config.is_caller_info_enabled)
            and (frame0 := inspect.currentframe())
            and (frame1 := frame0.f_back)
            # and (frame2 := frame1.f_back)
            and (caller_frame := frame1.f_back)
        ):
            caller_info = inspect.getframeinfo(caller_frame)
            caller_file = caller_info.filename
            cwd = os.getcwd()
            try:
                caller_file = os.path.relpath(caller_file, cwd)
            except ValueError:
                # This can happen if the file is on a different drive (on Windows)
                # In this case, we'll keep the absolute path
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

    def _log_message(
        self,
        message: str,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = None,
        inline: Optional[str] = None,
        include_exception: bool = False,
    ):
        """
        Logs a message to both console and Google Cloud.

        Args:
            message (str): The message to be logged.
            severity (int): The severity level of the log message.
            caller_info_str (Optional[str]): Information about the caller.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            inline (Optional[str], optional): Inline title for the log message. Defaults to None.
                Used to display the title inline, only if the title arg is None.
            include_exception (bool, optional): Whether to include exception traceback. Defaults to False.
        """
        if title is not None:
            message = f"{title}:\n{message}"
        elif inline is not None:
            message = f"{inline}: {message}"

        message_for_console = message
        if caller_info_str is not None:
            message_for_console = f"{caller_info_str}: {message}"

        if include_exception:
            message += f"\n{traceback.format_exc()}"
        self._log_to_console(message=message_for_console, severity=severity)

    def _log_data(
        self,
        data: Any,
        severity: int,
        caller_info_str: Optional[str],
        title: Optional[str] = None,
        include_exception: bool = False,
    ):
        """
        Logs potentially structured data (maybe it's a dict or a list) to both console and Google Cloud.

        Args:
            data (Any): The data to be logged.
            severity (int): The severity level of the log message.
            caller_info_str (Optional[str]): Information about the caller.
            title (Optional[str], optional): The title of the log message. Defaults to None.
            include_exception (bool, optional): Whether to include exception traceback. Defaults to False.
        """
        if data is None:
            message = "None"
            if title is not None:
                message = f"{title}:\n{message}"
            if caller_info_str is not None:
                message = f"{caller_info_str}: {message}"
            if include_exception:
                message += f"\n{traceback.format_exc()}"
            self._log_to_console(message=message, severity=severity)
        elif isinstance(data, dict):
            dict_string: str
            _, dict_string = purify_json_dict(
                data=data,
                indent=self._log_config.json_logs_indent,
                is_warning_enabled=True,
            )
            message = f"\n{dict_string}"
            if title is not None:
                message = f"{title}:{message}"
            if caller_info_str is not None:
                message = f"{caller_info_str}: {message}"
            if include_exception:
                message += f"\n{traceback.format_exc()}"
            self._log_to_console(message=message, severity=severity)
        elif isinstance(data, list):
            list_data: List[Any] = data
            _, list_string = purify_json_list(data=list_data, indent=self._log_config.json_logs_indent)
            message = f"\n{list_string}"
            if title is not None:
                message = f"{title}:{message}"
            if caller_info_str is not None:
                message = f"{caller_info_str}: {message}"
            if include_exception:
                message += f"\n{traceback.format_exc()}"
            self._log_to_console(message=message, severity=severity)
        else:
            _, dict_string = purify_json(
                data=data,
                indent=self._log_config.json_logs_indent,
                is_warning_enabled=False,
            )
            message = f"\n{dict_string}"
            if title is not None:
                message = f"{title}:{message}"
            if caller_info_str is not None:
                message = f"{caller_info_str}: {message}"
            if include_exception:
                message += f"\n{traceback.format_exc()}"
            self._log_to_console(message=message, severity=severity)

    def _log_to_console(self, message: str, severity: int):
        """
        Logs a message to the console.

        Args:
            message (str): The message to be logged.
            severity (int): The severity level of the log message.
        """
        if not self._log_config.is_console_logging_enabled:
            return

        if sandbox_manager.is_in_sandbox():
            logger = logging.getLogger(self._log_config.generic_poor_logger)
            logger.log(level=severity, msg=message, stacklevel=6)
            return

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

                    if hasattr(module, "__file__") and module.__file__ is not None:
                        module_file = os.path.abspath(module.__file__)
                    else:
                        continue

                    if module_file == logging_module_path or module_file.endswith("/log.py"):
                        continue
                    else:
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
