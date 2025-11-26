import logging
from typing import ClassVar

from pipelex.base_exceptions import PipelexError
from pipelex.types import StrEnum


class ToolError(PipelexError):
    pass


class NestedKeyConflictError(ToolError):
    """Raised when attempting to create nested keys under a non-dict value."""


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
