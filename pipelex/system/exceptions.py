import logging
from typing import ClassVar

from pipelex.base_exceptions import PipelexError
from pipelex.types import StrEnum


class ToolError(PipelexError):
    pass


class NestedKeyConflictError(ToolError):
    """Raised when attempting to create nested keys under a non-dict value."""


class MissingDependencyError(PipelexError):
    """Raised when a required dependency is not installed."""

    def __init__(self, dependency_name: str, extra_name: str, message: str | None = None):
        self.dependency_name = dependency_name
        self.extra_name = extra_name
        error_msg = f"Required dependency '{dependency_name}' is not installed."
        if message:
            error_msg += f" {message}"
        error_msg += f" Please install it with 'pip install pipelex[{extra_name}]'."
        super().__init__(error_msg)


class CredentialsError(PipelexError):
    pass


class TracebackMessageErrorMode(StrEnum):
    ERROR = "error"
    EXCEPTION = "exception"


class TracebackMessageError(PipelexError):
    error_mode: ClassVar[TracebackMessageErrorMode] = TracebackMessageErrorMode.EXCEPTION

    def __init__(self, message: str):
        super().__init__(message)
        logger_name = __name__
        match self.__class__.error_mode:
            case TracebackMessageErrorMode.ERROR:
                generic_poor_logger = "#poor-log"
                logger = logging.getLogger(generic_poor_logger)
                logger.error(message)
            case TracebackMessageErrorMode.EXCEPTION:
                self.logger = logging.getLogger(logger_name)
                self.logger.exception(message)


class FatalError(TracebackMessageError):
    pass


class ConfigValidationError(FatalError):
    pass


class ConfigModelError(ValueError, FatalError):
    pass
