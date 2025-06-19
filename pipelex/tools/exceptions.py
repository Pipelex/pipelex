import logging

from pipelex.tools.sandbox_manager import sandbox_manager


class RootException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ToolException(RootException):
    pass


class TracebackMessageError(RootException):
    def __init__(self, message: str):
        super().__init__(message)
        logger_name = __name__
        if sandbox_manager.is_in_sandbox():
            generic_poor_logger = "#sandbox"
            logger = logging.getLogger(generic_poor_logger)
            logger.error(message)
        else:
            self.logger = logging.getLogger(logger_name)
            self.logger.exception(message)


class FatalError(TracebackMessageError):
    pass


class ConfigValidationError(FatalError):
    pass


class ConfigNotFoundError(RootException):
    pass


class ConfigModelError(ValueError, FatalError):
    pass
