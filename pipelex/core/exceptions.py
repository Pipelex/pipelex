"""Custom exceptions for the Pipelex core module."""


class PipelexInterpreterError(Exception):
    """Base exception class for PipelexInterpreter errors."""

    pass


class PipelexConfigurationError(PipelexInterpreterError):
    """Raised when there are configuration issues with the PipelexInterpreter."""

    pass


class PipelexFileError(PipelexInterpreterError):
    """Raised when there are file-related issues in PipelexInterpreter."""

    pass


class PipelexUnknownPipeError(PipelexInterpreterError):
    """Raised when encountering an unknown pipe blueprint type."""

    pass
